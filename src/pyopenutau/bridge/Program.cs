// Optional compatibility probe and headless host bootstrap. Neither enters
// the GUI. State is isolated before deserializing any OpenUtau model.
using System.Collections;
using System.Reflection;
using System.Runtime.Loader;
using System.Runtime.CompilerServices;
using System.Linq.Expressions;
using System.Text.Json;

if (args.Length is not (2 or 3)) {
    Console.Error.WriteLine("usage: CoreCheck <OpenUtau assembly directory> <project.ustx>");
    return 2;
}
try {
    string root = Path.GetFullPath(args[0]);
    AssemblyLoadContext.Default.Resolving += (context, name) => {
        string path = Path.Combine(root, name.Name + ".dll");
        return File.Exists(path) ? context.LoadFromAssemblyPath(path) : null;
    };
    var core = AssemblyLoadContext.Default.LoadFromAssemblyPath(Path.Combine(root, "OpenUtau.Core.dll"));
    // OpenUtau's PathManager constructor can migrate/delete old caches, and
    // note presets can save defaults on first use. Never initialize that
    // singleton against the user's profile during a compatibility probe.
    // Bootstrap an isolated instance before deserializing any OpenUtau model.
    // This optional, .NET-8-specific adapter fails closed if internals change.
    var pathType = core.GetType("OpenUtau.Core.PathManager", true)!;
    var paths = RuntimeHelpers.GetUninitializedObject(pathType);
    string stateRoot = Path.Combine(Path.GetDirectoryName(Path.GetFullPath(args[1]))!, "core-state");
    Directory.CreateDirectory(stateRoot);
    pathType.GetProperty("RootPath")!.SetValue(paths, root);
    pathType.GetProperty("DataPath")!.SetValue(paths, stateRoot);
    pathType.GetProperty("CachePath")!.SetValue(paths, stateRoot);
    pathType.GetProperty("HomePathIsAscii")!.SetValue(paths, true);
    object lazyPaths = pathType.BaseType!.GetField("inst", BindingFlags.NonPublic | BindingFlags.Static)!.GetValue(null)!;
    var factory = lazyPaths.GetType().GetField("_factory", BindingFlags.NonPublic | BindingFlags.Instance)
        ?? throw new NotSupportedException("This .NET Lazy implementation cannot isolate OpenUtau state");
    factory.SetValue(lazyPaths, Expression.Lambda(factory.FieldType, Expression.Constant(paths, pathType)).Compile());
    object initializedPaths = pathType.BaseType!.GetProperty("Inst")!.GetValue(null)!;
    if (!ReferenceEquals(initializedPaths, paths)) {
        throw new InvalidOperationException("OpenUtau state was initialized before isolation; refusing to continue");
    }
    object Get(object obj, string member) => obj.GetType().GetField(member)?.GetValue(obj)
        ?? obj.GetType().GetProperty(member)?.GetValue(obj)
        ?? throw new InvalidDataException($"Null/missing {obj.GetType().Name}.{member}");
    IEnumerable<object> Items(object obj, string member) => ((IEnumerable)Get(obj, member)).Cast<object>();
    var projectType = core.GetType("OpenUtau.Core.Ustx.UProject", true)!;
    var yamlType = core.GetType("OpenUtau.Core.Yaml", true)!;
    object yaml = yamlType.GetProperty("DefaultDeserializer")!.GetValue(null)!;
    var deserialize = yamlType.GetMethods().Single(m => m.Name == "Deserialize"
        && m.IsGenericMethod && m.GetParameters()[0].ParameterType == typeof(string));
    object project = deserialize.MakeGenericMethod(projectType).Invoke(yaml, new object[] { File.ReadAllText(args[1]) })!;
    var formatType = core.GetType("OpenUtau.Core.Format.Ustx", true)!;
    var supported = (Version)formatType.GetField("kUstxVersion")!.GetValue(null)!;
    var version = (Version)Get(project, "ustxVersion");
    if (version > supported) throw new InvalidDataException($"Project {version} is newer than core {supported}");
    if (args.Length == 3) {
        string result = JsonSerializer.Serialize(EngineHost.Run(core, root, project, args[2]));
        // Native stdout is not a reliable result channel (some libraries log
        // without a newline). Keep the final response on a separate job file.
        File.WriteAllText(Path.Combine(Path.GetDirectoryName(Path.GetFullPath(args[2]))!, "result.json"), result);
        return 0;
    }
    object axis = Get(project, "timeAxis");
    axis.GetType().GetMethod("BuildSegments")!.Invoke(axis, new[] { project });
    var tracks = Items(project, "tracks").ToArray();
    int count = 0;
    var points = new List<object>();
    // Do not call AfterLoad/ValidateFull: those resolve installed singers and
    // schedule plugins. Validate each note against OpenUtau's real time axis.
    var optionsType = core.GetType("OpenUtau.Core.ValidateOptions", true)!;
    object options = Activator.CreateInstance(optionsType)!;
    optionsType.GetField("SkipPhonemizer")!.SetValue(options, true);
    optionsType.GetField("SkipPhoneme")!.SetValue(options, true);
    foreach (object part in Items(project, "voiceParts")) {
        int trackNo = (int)Get(part, "trackNo");
        foreach (object note in Items(part, "notes")) {
            _ = Get(note, "vibrato");
            object pitch = Get(note, "pitch");
            var data = Items(pitch, "data").ToArray();
            if (data.Length < 2) throw new InvalidDataException("Pitch needs at least two points");
            note.GetType().GetMethod("Validate")!.Invoke(note, new[] { options, project, tracks[trackNo], part });
            points.Add(new { tone = Get(note, "tone"), position_ms = Get(note, "PositionMs"),
                             first_pitch_y = Get(data[0], "Y") });
            count++;
        }
    }
    Console.WriteLine(JsonSerializer.Serialize(new {
        core_version = core.GetName().Version!.ToString(), project_version = version.ToString(),
        supported_version = supported.ToString(), tracks = tracks.Length, notes = count,
        isolated_state = true,
        note_details = points,
        scope = "OpenUtau deserialization, time-axis construction and note validation; no phonemization or rendering"
    }));
    return 0;
} catch (Exception error) {
    while (error is TargetInvocationException && error.InnerException != null) error = error.InnerException;
    Console.Error.WriteLine(error.ToString());
    return 1;
}
