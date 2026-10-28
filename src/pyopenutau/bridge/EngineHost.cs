// Versioned headless adapter to the real OpenUtau core. No GUI entry point.
using System.Collections;
using System.Collections.Concurrent;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.Json;

static class R {
    const BindingFlags Flags = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance;
    public static object? Maybe(object obj, string key) => obj.GetType().GetField(key, Flags)?.GetValue(obj)
        ?? obj.GetType().GetProperty(key, Flags)?.GetValue(obj);
    public static object Get(object obj, string key) => Maybe(obj, key)
        ?? throw new InvalidDataException($"Missing {obj.GetType().Name}.{key}");
    public static void Set(object obj, string key, object? value) {
        var field = obj.GetType().GetField(key, Flags);
        if (field != null) field.SetValue(obj, value);
        else (obj.GetType().GetProperty(key, Flags) ?? throw new MissingMemberException(key)).SetValue(obj, value);
    }
    public static object? Call(object obj, string method, params object?[] args) => obj.GetType()
        .GetMethods(Flags).Single(m => m.Name == method && m.GetParameters().Length == args.Length).Invoke(obj, args);
    public static IEnumerable<object> Items(object obj, string key) => ((IEnumerable)Get(obj, key)).Cast<object>();
    public static object Instance(Type type) => type.BaseType!.GetProperty("Inst")!.GetValue(null)!;
}

// OpenUtau's document callbacks must execute on the document thread. Never
// substitute a thread-pool scheduler or recursively invoke its UI callback.
sealed class Pump : TaskScheduler, IDisposable {
    readonly BlockingCollection<Task> pending = new();
    protected override void QueueTask(Task task) => pending.Add(task);
    protected override bool TryExecuteTaskInline(Task task, bool queued) => false;
    protected override IEnumerable<Task>? GetScheduledTasks() => pending.ToArray();
    public void Post(Action action) => Task.Factory.StartNew(action, CancellationToken.None, TaskCreationOptions.None, this);
    void Execute(Task task) { TryExecuteTask(task); task.GetAwaiter().GetResult(); }
    public void Step() { if (pending.TryTake(out var task, 10)) Execute(task); }
    public void Until(Func<bool> done) { while (!done()) Step(); while (pending.TryTake(out var task)) Execute(task); }
    public void Dispose() => pending.Dispose();
}

static class EngineHost {
    static void Progress(string stage, double? fraction = null) => Console.WriteLine(JsonSerializer.Serialize(
        new { protocol_version = 1, type = "progress", stage, fraction }));

    public static object Run(Assembly core, string root, object project, string requestPath) {
        Encoding.RegisterProvider(CodePagesEncodingProvider.Instance);
        using var request = JsonDocument.Parse(File.ReadAllText(requestPath));
        var spec = request.RootElement;
        if (!spec.TryGetProperty("protocol_version", out var protocol) || protocol.GetInt32() != 1)
            throw new NotSupportedException("Unsupported pyopenutau host protocol; expected version 1");
        string mode = spec.GetProperty("mode").GetString()!;
        Type Type(string name) => core.GetType(name, true)!;
        var factoryType = Type("OpenUtau.Api.PhonemizerFactory");
        var phonemizerType = Type("OpenUtau.Api.Phonemizer");
        var assemblies = new List<Assembly> { core };
        string builtins = Path.Combine(root, "OpenUtau.Plugin.Builtin.dll");
        if (File.Exists(builtins)) assemblies.Add(Assembly.LoadFrom(builtins));
        var factories = new List<object>();
        foreach (var assembly in assemblies) {
            foreach (var type in assembly.GetExportedTypes().Where(t => !t.IsAbstract && t.IsSubclassOf(phonemizerType))) {
                var factory = factoryType.GetMethod("Get", new[] { typeof(Type) })!.Invoke(null, new object[] { type });
                if (factory != null) factories.Add(factory);
            }
        }
        factoryType.GetMethod("BuildList")?.Invoke(null, null);
        if (mode == "capabilities") {
            bool canRender = Type("OpenUtau.Core.Render.RenderEngine").GetMethods().Any(m => m.Name == "RenderMixdown" && m.GetParameters().Length == 3);
            return new { protocol_version = 1, type = "result", data = new {
                core_version = core.GetName().Version!.ToString(),
                supported_version = Type("OpenUtau.Core.Format.Ustx").GetField("kUstxVersion")!.GetValue(null)!.ToString(),
                renderers = canRender ? new[] { "WORLDLINE-R" } : Array.Empty<string>(),
                phonemizers = factories.Select(f => new { class_name = ((Type)R.Get(f, "type")).FullName,
                    name = R.Get(f, "name"), tag = R.Get(f, "tag"), language = R.Maybe(f, "language") }).ToArray()
            }};
        }
        object LoadBank(string path) {
            string character = Path.Combine(Path.GetFullPath(path), "character.txt");
            if (!File.Exists(character)) throw new FileNotFoundException("Singer needs character.txt", character);
            var bank = Activator.CreateInstance(Type("OpenUtau.Classic.Voicebank"))!;
            Type("OpenUtau.Classic.VoicebankLoader").GetMethod("LoadInfo")!.Invoke(null,
                new object[] { bank, character, Directory.GetParent(Path.GetDirectoryName(character)!)!.FullName });
            return bank;
        }
        if (mode == "otos") {
            object bank = LoadBank(spec.GetProperty("path").GetString()!);
            if (R.Get(bank, "SingerType").ToString() != "Classic") throw new NotSupportedException("OTO inspection needs a Classic bank");
            object singer = Activator.CreateInstance(Type("OpenUtau.Classic.ClassicSinger"), bank)!;
            R.Call(singer, "EnsureLoaded");
            return new { protocol_version = 1, type = "result", data = new { otos = R.Items(singer, "Otos").Select(oto => new {
                alias = R.Get(oto, "Alias"), sample_path = R.Get(oto, "File"), offset_ms = R.Get(oto, "Offset"),
                consonant_ms = R.Get(oto, "Consonant"), cutoff_ms = R.Get(oto, "Cutoff"),
                preutter_ms = R.Get(oto, "Preutter"), overlap_ms = R.Get(oto, "Overlap") }).ToArray() } };
        }
        if (mode == "singers") {
            var singers = new List<object>();
            var seen = new HashSet<string>(OperatingSystem.IsWindows() ? StringComparer.OrdinalIgnoreCase : StringComparer.Ordinal);
            foreach (var searchPath in spec.GetProperty("search_paths").EnumerateArray()) {
                string search = Path.GetFullPath(searchPath.GetString()!);
                foreach (string character in Directory.EnumerateFiles(search, "character.txt", SearchOption.AllDirectories).OrderBy(p => p, StringComparer.Ordinal)) {
                    if (!seen.Add(character)) continue;
                    string directory = Path.GetDirectoryName(character)!;
                    object bank = LoadBank(directory);
                    singers.Add(new { id = R.Get(bank, "Id"), name = R.Get(bank, "Name"), path = directory,
                                      singer_type = R.Get(bank, "SingerType").ToString() });
                }
            }
            return new { protocol_version = 1, type = "result", data = new { singers } };
        }
        if (mode is not ("phonemize" or "render")) throw new NotSupportedException($"Unknown operation {mode}");
        if (R.Items(project, "waveParts").Any()) throw new NotSupportedException("Headless vocal rendering does not yet support wave parts");
        var manager = R.Instance(Type("OpenUtau.Core.SingerManager"));
        var registry = (IDictionary)R.Get(manager, "Singers");
        foreach (var binding in spec.GetProperty("singers").EnumerateObject()) {
            object bank = LoadBank(binding.Value.GetString()!);
            if (R.Get(bank, "SingerType").ToString() != "Classic")
                throw new NotSupportedException("This headless host currently supports Classic voicebanks only");
            registry[binding.Name] = Activator.CreateInstance(Type("OpenUtau.Classic.ClassicSinger"), bank)!;
        }
        var projectTracks = R.Items(project, "tracks").ToArray();
        var expectedPhonemizers = new List<string>();
        var selectedFactories = new List<object>();
        for (int ti = 0; ti < projectTracks.Length; ti++) {
            object track = projectTracks[ti];
            bool hasNotes = R.Items(project, "voiceParts").Any(p => (int)R.Get(p, "trackNo") == ti && R.Items(p, "notes").Any());
            string singer = (string?)R.Maybe(track, "singer") ?? "";
            if (hasNotes && !registry.Contains(singer)) throw new InvalidDataException($"No singer binding for track {ti} singer '{singer}'");
            string phonemizer = (string?)R.Maybe(track, "phonemizer") ?? "OpenUtau.Core.DefaultPhonemizer";
            object? selectedFactory = factories.FirstOrDefault(f => {
                var type = (Type)R.Get(f, "type");
                return type.FullName == phonemizer || type.AssemblyQualifiedName == phonemizer;
            });
            if (selectedFactory == null)
                throw new NotSupportedException($"Phonemizer not found in installed core/builtins: {phonemizer}");
            expectedPhonemizers.Add(((Type)R.Get(selectedFactory, "type")).FullName!);
            selectedFactories.Add(selectedFactory);
            // Older UTrack.AfterLoad uses GUI factory-list state. Initialize
            // the explicitly requested factory ourselves, then prevent that
            // code path from silently replacing it with the default plugin.
            R.Set(track, "phonemizer", null);
            object settings = R.Get(track, "RendererSettings");
            string renderer = (string?)R.Maybe(settings, "renderer") ?? "WORLDLINE-R";
            if (renderer != "WORLDLINE-R") throw new NotSupportedException($"Unsupported headless renderer '{renderer}'; use WORLDLINE-R");
            string? resampler = (string?)R.Maybe(settings, "resampler");
            if (!string.IsNullOrEmpty(resampler) && resampler != "worldline")
                throw new NotSupportedException($"Unsupported headless resampler '{resampler}'; use worldline or None");
            if (!string.IsNullOrEmpty((string?)R.Maybe(settings, "wavtool")))
                throw new NotSupportedException("WORLDLINE-R does not use an external wavtool; leave wavtool=None");
            R.Set(settings, "renderer", renderer);
        }
        NativeLibrary.SetDllImportResolver(core, (name, assembly, path) => {
            string file = OperatingSystem.IsMacOS() ? $"lib{name}.dylib" : OperatingSystem.IsWindows() ? $"{name}.dll" : $"lib{name}.so";
            string full = Path.Combine(root, file);
            return File.Exists(full) ? NativeLibrary.Load(full) : IntPtr.Zero;
        });
        R.Call(R.Instance(Type("OpenUtau.Classic.ToolsManager")), "SearchResamplers");
        using var pump = new Pump();
        object doc = R.Instance(Type("OpenUtau.Core.DocManager"));
        R.Set(doc, "mainThread", Thread.CurrentThread);
        R.Set(doc, "mainScheduler", pump);
        R.Set(doc, "PostOnUIThread", (Action<Action>)pump.Post);
        R.Set(doc, "Project", project);
        var factoryArray = Array.CreateInstance(factoryType, factories.Count);
        for (int i = 0; i < factories.Count; i++) factoryArray.SetValue(factories[i], i);
        R.Set(doc, "PhonemizerFactories", factoryArray);
        object runner = Activator.CreateInstance(Type("OpenUtau.Api.PhonemizerRunner"), pump)!;
        R.Set(doc, "PhonemizerRunner", runner);
        try {
            Progress("phonemizing");
            for (int ti = 0; ti < projectTracks.Length; ti++)
                R.Set(projectTracks[ti], "Phonemizer", R.Call(selectedFactories[ti], "Create"));
            R.Call(project, "AfterLoad");
            for (int ti = 0; ti < projectTracks.Length; ti++) {
                if (R.Get(projectTracks[ti], "Phonemizer").GetType().FullName != expectedPhonemizers[ti])
                    throw new InvalidDataException($"Track {ti}: phonemizer initialization fell back instead of loading {expectedPhonemizers[ti]}");
            }
            // This derived state normally comes from the GUI's JudgeMuted.
            // Reproduce that initialization; mixing itself stays in OpenUtau.
            bool anySolo = projectTracks.Any(t => (bool)R.Get(t, "Solo"));
            foreach (object track in projectTracks) R.Set(track, "Muted", !(bool)R.Get(track, "Solo") && ((bool)R.Get(track, "Mute") || anySolo));
            R.Call(project, "ValidateFull");
            var parts = R.Items(project, "parts").Where(p => p.GetType().Name == "UVoicePart").ToArray();
            pump.Until(() => parts.All(p => (bool)R.Get(p, "PhonemesUpToDate")));
            var phones = new List<object>();
            var diagnostics = new List<object>();
            for (int pi = 0; pi < parts.Length; pi++) {
                object part = parts[pi];
                int trackIndex = (int)R.Get(part, "trackNo");
                int partIndex = parts.Take(pi).Count(p => (int)R.Get(p, "trackNo") == trackIndex);
                var notes = R.Items(part, "notes").ToArray();
                foreach (object phone in R.Items(part, "phonemes")) {
                    int ni = Array.IndexOf(notes, R.Get(phone, "Parent"));
                    bool error = (bool)R.Get(phone, "Error");
                    object? oto = R.Maybe(phone, "oto");
                    phones.Add(new { track_index = trackIndex, part_index = partIndex, note_index = ni,
                        phoneme_index = R.Get(phone, "index"), phoneme = R.Get(phone, "phoneme"),
                        mapped_alias = R.Maybe(phone, "phonemeMapped"), position_ticks = R.Get(phone, "position"),
                        duration_ticks = R.Get(phone, "Duration"), position_ms = R.Get(phone, "PositionMs"),
                        duration_ms = R.Get(phone, "DurationMs"), preutter_ms = R.Get(phone, "preutter"),
                        overlap_ms = R.Get(phone, "overlap"), sample_path = oto == null ? null : R.Maybe(oto, "File"), error });
                    if (error) diagnostics.Add(new { code = "phoneme_error", severity = "error",
                        message = R.Maybe(phone, "ErrorException")?.ToString() ?? $"Unrenderable phoneme {R.Get(phone, "phoneme")}",
                        track_index = trackIndex, part_index = partIndex, note_index = ni });
                }
                if (notes.Length > 0 && !R.Items(part, "phonemes").Any())
                    diagnostics.Add(new { code = "no_phonemes", severity = "error", message = "Part produced no phonemes",
                        track_index = trackIndex, part_index = partIndex, note_index = -1 });
                foreach (object phrase in R.Items(part, "renderPhrases")) {
                    foreach (object phone in R.Items(phrase, "phones")) {
                        string? selectedResampler = (string?)R.Maybe(phone, "resampler");
                        if (!string.IsNullOrEmpty(selectedResampler) && selectedResampler != "worldline")
                            throw new NotSupportedException($"Unsupported per-phoneme resampler '{selectedResampler}'");
                    }
                }
            }
            if (mode == "phonemize") return new { protocol_version = 1, type = "result", data = new { phonemes = phones, diagnostics,
                core_version = core.GetName().Version!.ToString() } };
            if (diagnostics.Count != 0) throw new InvalidDataException("Phonemization errors; inspect phonemize() diagnostics before rendering");
            Progress("rendering");
            var engineType = Type("OpenUtau.Core.Render.RenderEngine");
            object engine = Activator.CreateInstance(engineType, project, 0, -1, -1)!;
            var method = engineType.GetMethods().FirstOrDefault(m => m.Name == "RenderMixdown" && m.GetParameters().Length == 3)
                ?? throw new NotSupportedException("Installed OpenUtau lacks the supported RenderMixdown API");
            var task = Task.Run(() => method.Invoke(engine, new object?[] { pump, null, true })!);
            pump.Until(() => task.IsCompleted);
            object mix = R.Get(task.GetAwaiter().GetResult(), "Item1");
            var audio = new List<float>();
            int position = 0;
            while (true) {
                float[] buffer = new float[8192];
                int endPosition = (int)R.Call(mix, "Mix", position, buffer, 0, buffer.Length)!;
                int count = Math.Max(0, endPosition - position);
                if (count == 0) break;
                if (count > buffer.Length) throw new InvalidDataException("Invalid engine mix position");
                audio.AddRange(buffer.Take(count));
                position = endPosition;
                if (position > 44100 * 2 * 60 * 60) throw new InvalidDataException("Render exceeds the one-hour safety limit");
            }
            if (audio.Count == 0 && projectTracks.All(t => (bool)R.Get(t, "Muted"))) {
                int lastNote = parts.SelectMany(p => R.Items(p, "notes").Select(n =>
                    (int)R.Get(p, "position") + (int)R.Get(n, "position") + (int)R.Get(n, "duration"))).DefaultIfEmpty(0).Max();
                double endMs = (double)R.Call(R.Get(project, "timeAxis"), "TickPosToMsPos", (double)lastNote)!;
                int silentFrames = (int)Math.Ceiling(endMs * 44.1);
                if (silentFrames > 44100 * 60 * 60) throw new InvalidDataException("Render exceeds the one-hour safety limit");
                audio.AddRange(new float[silentFrames * 2]);
            }
            if (audio.Count == 0 || audio.Any(f => !float.IsFinite(f))) throw new InvalidDataException("Empty/nonfinite engine render");
            float peak = audio.Max(f => Math.Abs(f));
            if (peak > 1) diagnostics.Add(new { code = "peak_above_full_scale", severity = "warning",
                message = "Float WAV preserves peaks above 1; playback or PCM conversion may clip. Lower track volume.",
                track_index = -1, part_index = -1, note_index = -1 });
            string output = spec.GetProperty("output").GetString()!;
            using (var writer = new BinaryWriter(new FileStream(output, FileMode.CreateNew))) {
                writer.Write(Encoding.ASCII.GetBytes("RIFF")); writer.Write(36 + audio.Count * 4);
                writer.Write(Encoding.ASCII.GetBytes("WAVEfmt ")); writer.Write(16); writer.Write((short)3);
                writer.Write((short)2); writer.Write(44100); writer.Write(44100 * 8); writer.Write((short)8); writer.Write((short)32);
                writer.Write(Encoding.ASCII.GetBytes("data")); writer.Write(audio.Count * 4);
                foreach (float sample in audio) writer.Write(sample);
            }
            return new { protocol_version = 1, type = "result", data = new { sample_rate = 44100, channels = 2, frames = audio.Count / 2,
                peak_abs = peak, core_version = core.GetName().Version!.ToString(), diagnostics } };
        } finally { ((IDisposable)runner).Dispose(); }
    }
}
