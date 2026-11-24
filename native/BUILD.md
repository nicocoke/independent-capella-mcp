# Native build

The preview targets the Windows Capella `7.1.0.202606231255` product and Sirius `7.4.14.202512030914`. Use Java 17 and Maven with a prepared 7.1.0 Eclipse target. The Tycho profile reads an absolute target file through `capella71.target`.

```powershell
mvn -f native/pom.xml "-Dcapella71.target=C:/path/to/capella-7.1.0.target" package -DskipTests
```

The update-site ZIP is produced under `native/repository/target/`. The historical target selected in the absence of `capella71.target` uses Capella 7.0.1.

For a local target, `tools/target_from_disposable.py` converts the p2 profile of a **prepared disposable Capella product** into a local target repository. It expects the full product profile with the matching Eclipse Orbit Gson bundle and an extraction receipt identifying the disposable copy. It writes p2 metadata into the supplied product directory.

```powershell
python -B tools/target_from_disposable.py --version 7.1.0 --product C:/scratch/runtime/pilot/capella --target C:/scratch/capella-7.1.0.target
```

Put the receipt at `C:/scratch/runtime/extraction-complete.json`. Its `source` must be the official Capella 7.1.0 download URL, and its `destination` must be the absolute path of the parent of the extracted `capella` directory. Use the SHA-512 in the disposable runner to verify the release archive before extraction. The tool expects the Gson dependency to appear in the disposable product's p2 profile. The release installation guide describes how to install the matching feature and dependency.

The public starter contains the local target generator. Clean native target bootstrapping and a public CI build of the shipping update site still need verification. For the initial demo, use the tested release assets. See [the isolated trial procedure](../docs/ISOLATED-TRIAL.md) and [verification](../docs/VERIFICATION.md).
