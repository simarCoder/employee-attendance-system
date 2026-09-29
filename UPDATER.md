# Windows releases and automatic updates

The packaged application checks the latest non-prerelease GitHub release when it
starts. It only downloads after the user chooses **Update now**. The downloaded
release ZIP is checked against the SHA-256 digest reported by GitHub before its
two executables are staged. A side-by-side updater helper waits for the app to
close, moves the previous executable(s) into `old_files`, installs the new
executables, then starts the updated app. The database and user files are left
in place.

## Publishing an update

1. Set `APP_VERSION` in `app_version.py` to the release version, such as
   `1.0.1`, and commit the change.
2. Push a matching version tag, for example `v1.0.1`.
3. The `Build and publish Windows release` workflow builds the Windows app and
   updater helper, packages them as `HR_Management_System-win64.zip`, and
   publishes a GitHub release. The updater discovers that exact asset name.

Keep the release public so the installed app can read it without credentials.
The initial installation must include both `HR_Management_System.exe` and
`HR_Management_System_Updater.exe` in the same writable folder. For example,
distribute the ZIP from the release and extract both files together. The
application's `db`, `UPLOADS`, and other local data folders stay beside the EXE
and are not replaced by an update.

The install folder must be writable by the employee running the app. Avoid
installing into a protected Windows location such as `Program Files` unless
the application is installed there with suitable permissions.
