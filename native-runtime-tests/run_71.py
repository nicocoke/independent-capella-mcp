"""Run native regression checks only in a fresh copy of the pinned public Capella product."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import zipfile

PRODUCT = "capella-7.1.0.202606231255-win32-win32-x86_64.zip"
SHA512 = "315b13e46086a8ffef8cd661eea2ffc5ff2cbbab17fbb545080d1d64ca9cfa9781b352afa214336f6eec0432b1c8e087ede379a4a0e9b252ee50c07f0d1abdfb"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--product-zip", type=Path, required=True,
                        help=f"Official Windows release archive named {PRODUCT}")
    parser.add_argument("--update-site", type=Path, required=True,
                        help="Matching Independent Capella MCP update-site zip")
    parser.add_argument("--jdk", type=Path, required=True, help="JDK 17 installation directory")
    parser.add_argument("--work-dir", type=Path, default=Path("work"),
                        help="Parent directory for a new disposable product and workspace")
    args = parser.parse_args()
    package = Path(__file__).resolve().parents[1]
    archive = args.product_zip.resolve(strict=True)
    java_bin = args.jdk.resolve(strict=True) / "bin"
    site = args.update_site.resolve(strict=True)
    if os.name != "nt" or not site.is_file() or not (java_bin / "javac.exe").is_file():
        raise RuntimeError("Windows, the matching update-site ZIP and JDK 17 are required")
    with archive.open("rb") as stream:
        if hashlib.file_digest(stream, "sha512").hexdigest() != SHA512:
            raise ValueError("Unexpected product archive")
    scratch = args.work_dir.resolve()
    scratch.mkdir(parents=True, exist_ok=True)
    trial = Path(tempfile.mkdtemp(prefix="native71-", dir=scratch)).resolve()
    product = trial / "capella"
    with zipfile.ZipFile(archive) as bundle:
        entries = [e for e in bundle.infolist() if e.filename.startswith("capella/")]
        if not entries or any(not (trial / e.filename).resolve().is_relative_to(product) for e in entries):
            raise ValueError("Unexpected product content")
        bundle.extractall(chr(92)*2 + "?" + chr(92) + str(trial), entries)
    plugins = product / "plugins"
    registration = product / "configuration/org.eclipse.equinox.simpleconfigurator/bundles.info"
    lines = registration.read_text().splitlines()
    with zipfile.ZipFile(site) as bundle:
        entries = [n for n in bundle.namelist() if n.startswith("plugins/") and n.endswith(".jar")]
        if len(entries) != 2:
            raise ValueError("Expected the connector and Gson")
        for entry in entries:
            filename = entry.removeprefix("plugins/")
            match = re.fullmatch(r"(org\.example\.capella\.mcp|com\.google\.gson)_([\w.-]+)\.jar", filename)
            if not match:
                raise ValueError("Unexpected update site bundle")
            (plugins / filename).write_bytes(bundle.read(entry))
            lines = [line for line in lines if not line.startswith(match[1] + ",")]
            lines.append(f"{match[1]},{match[2]},plugins/{filename},4,false")
    env = dict(os.environ)
    for key, path in {"USERPROFILE":"home","APPDATA":"home/roaming","LOCALAPPDATA":"home/local",
                      "TMP":"tmp","TEMP":"tmp"}.items():
        folder = trial / path
        folder.mkdir(parents=True, exist_ok=True)
        env[key] = str(folder)
    home = trial / "home"
    empty_git = home / "empty-git-config"
    empty_git.touch()
    env.update(HOMEDRIVE=trial.drive, HOMEPATH=str(home)[len(trial.drive):],
               GIT_CONFIG_GLOBAL=str(empty_git), GIT_CONFIG_SYSTEM=str(empty_git))
    classes = trial / "classes"
    classes.mkdir()
    cp = ";".join(jar.as_posix() for jar in sorted(plugins.glob("*.jar")) if ".source_" not in jar.name)
    harness = package / "native-runtime-tests"
    sources = sorted((harness / "src").rglob("*.java"))
    argsfile = trial / "javac.args"
    argsfile.write_text("\n".join(f'"{s}"' for s in ["-encoding","UTF-8","-cp",cp,"-d",classes.as_posix(),
                                                     *(src.as_posix() for src in sources)]))
    subprocess.run([java_bin / "javac.exe", "@" + str(argsfile)], cwd=trial, env=env, check=True, timeout=180)
    test_jar = plugins / "org.example.capella.mcp.tests_0.1.0.jar"
    with zipfile.ZipFile(test_jar, "w", zipfile.ZIP_DEFLATED) as bundle:
        for name in ("META-INF/MANIFEST.MF","plugin.xml"):
            bundle.write(harness / name, name)
        for item in classes.rglob("*.class"):
            bundle.write(item, item.relative_to(classes).as_posix())
    lines.append("org.example.capella.mcp.tests,0.1.0,plugins/" + test_jar.name + ",4,false")
    for index, line in enumerate(lines):
        if line.startswith(("org.eclipse.equinox.p2.reconciler.dropins,", "org.eclipse.update.configurator,")):
            lines[index] = line.rsplit(",",1)[0] + ",false"
    registration.write_text("\n".join(lines) + "\n")
    import sys
    sys.path.insert(0, str(package))
    from capella_groundwork.compiler import compile_plan
    plan = json.loads((package / "examples/native-monitoring.json").read_text())
    (trial / "intent.json").write_text(json.dumps(compile_plan(plan)))
    (trial / "workspace").mkdir()
    (trial / "AUTHORIZED-SYNTHETIC-ONLY").write_text("Fresh pinned product and disposable model only.")
    preferences = trial / "defaults.ini"
    preferences.write_text("org.eclipse.ui/showIntro=false\norg.eclipse.ui/SHOW_PROGRESS_ON_STARTUP=false\n")
    launcher, = plugins.glob("org.eclipse.equinox.launcher_*.jar")
    command = [java_bin / "java.exe","-Xms128m","-Xmx1024m","-Xss4m","-Dosgi.locking=java.io",
               "-Duser.home="+str(home),"-Djava.io.tmpdir="+str(trial/"tmp"),
               "-Dcapella.mcp.expected.version=7.1.0","-Dcapella.mcp.disposable.test="+str(trial),
               "-Dosgi.install.area="+product.as_uri()+"/","-Declipse.launcher="+str(product/"capella.exe"),
               "-jar",launcher,"-nosplash","-clean","-consoleLog","-configuration",product/"configuration",
               "-data",trial/"workspace","-pluginCustomization",preferences]
    print("Disposable trial",trial,flush=True)
    try:
        with (trial/"console.log").open("w") as console:
            subprocess.run(command, cwd=product, env=env, stdout=console, stderr=subprocess.STDOUT, check=True,
                           creationflags=subprocess.CREATE_NO_WINDOW, timeout=420)
    finally:
        remaining = [line for line in registration.read_text().splitlines()
                     if not line.startswith("org.example.capella.mcp.tests,")]
        registration.write_text("\n".join(remaining) + "\n")
    report = json.loads((trial/"native-result.json").read_text())
    if report["status"] != "passed" or not all(check["passed"] for check in report["checks"]):
        raise RuntimeError("See native-result.json in the disposable trial")
    print(len(report["checks"]), "native checks passed")


if __name__ == "__main__":
    main()
