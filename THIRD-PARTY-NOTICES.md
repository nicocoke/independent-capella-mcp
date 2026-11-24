# Third-party content

The separate Windows x64 MCPB includes the official Python 3.14.10 embeddable distribution, SHA-256 `90905e64a840557d8c1bc4f5b74db3d7ee85e3ffb217611cac1c7813acea4159`, downloaded from Python.org. Its original `runtime/LICENSE.txt` is retained and covers Python and its included dependencies. The only runtime configuration modification is `python314._pth`, which restricts imports to the bundled runtime and server and leaves site loading disabled. `RUNTIME-PROVENANCE.json` in the MCPB records the original URL, release/checksum source and modification. No Python installer runs and no system Python is changed.

The update-site archive includes the unmodified Eclipse Orbit bundle `com.google.gson` version `2.10.1.v20230109-0753`, containing Google's Gson 2.10.1 under Apache License 2.0. It was resolved from the public Eclipse 2023-03 target repository.

The original bundle retains its embedded `about.html` and `about_files/APACHE-2.0.txt`. Copies are also provided in `third_party/gson/`. The Orbit notice describes applicable Eclipse packaging terms and identifies the third-party Gson license. No Gson source was modified.

Capella, EMF, Sirius and other platform components remain external runtime/build dependencies under their respective licenses. Their installation archives and build-tool binaries are not redistributed in this delivery. The new project's own distribution license has not been selected.
