# Security and trust boundary

Use trusted OpenUtau installations, native libraries, plugins and voicebanks.
The bridge launches local .NET/native code. Its fresh profile/cache directories
protect against accidentally sharing desktop state; they are **not an OS sandbox**.
The SDK cannot constrain a plugin's filesystem or network access.

USTX/YAML is parsed without arbitrary Python object construction, but input
documents can still consume memory or exercise downstream OpenUtau code. Do not
expose this synchronous library as an unauthenticated public rendering service.
Enforce your own resource limits and OS-level isolation for untrusted inputs.

Outputs refuse overwriting by default. Bank files are treated as read-only;
tests check synthetic inputs remain unchanged. Protect your original work with
backups; this is experimental software, not a transactional storage system.

Do not post credentials, private recordings, complete commercial voicebanks, or
personal filesystem paths in public issues. For a suspected vulnerability, use
the repository's private vulnerability-reporting feature if enabled. If it is
not available, request a private contact channel without publishing exploit
details. No response-time guarantee or formal support commitment is implied.
