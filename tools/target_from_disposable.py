from pathlib import Path
import argparse
import copy
import gzip
import json
import re
import xml.etree.ElementTree as ET
import zipfile


def generate(product, output, version):
    product = product.resolve(strict=True)
    receipt_path = product.parent.parent / 'extraction-complete.json'
    receipt = json.loads(receipt_path.read_text())
    if not receipt['source'].startswith('https://download.eclipse.org/capella/core/products/releases/' + version + '/'):
        raise ValueError('Only the verified disposable release copy is supported')
    if Path(receipt['destination']).resolve() != product.parent:
        raise ValueError('Product does not match the disposable extraction receipt')
    registry = product / 'p2/org.eclipse.equinox.p2.engine/profileRegistry/DefaultProfile.profile'
    candidates = sorted(registry.glob('*.profile.gz'), key=lambda path: int(path.name.split('.')[0]), reverse=True)
    units = None
    for candidate in candidates:
        profile = ET.fromstring(gzip.decompress(candidate.read_bytes()))
        inventory = profile.findall('./units/unit')
        if len(inventory) > 100:
            units = inventory
            break
    if units is None:
        raise ValueError('Full disposable product profile not found')
    repository = ET.Element('repository', name='Disposable Capella ' + version,
        type='org.eclipse.equinox.internal.p2.metadata.repository.LocalMetadataRepository', version='1')
    repository_units = ET.SubElement(repository, 'units')
    available = {}
    artifacts = ET.parse(product / 'artifacts.xml')
    artifact_entries = {(entry.get('id'), entry.get('version')): entry for entry in artifacts.findall('./artifacts/artifact') if entry.get('classifier') == 'osgi.bundle'}
    for unit in units:
        identifier = unit.get('id')
        release = unit.get('version')
        if not identifier or not release or not re.fullmatch(r'[A-Za-z0-9._-]+', identifier) or not re.fullmatch(r'[A-Za-z0-9._-]+', release):
            raise ValueError('Invalid bundle identifier or version in disposable inventory')
        if identifier.startswith('org.example.capella.mcp'):
            continue
        if not any(artifact.get('classifier') == 'osgi.bundle' for artifact in unit.findall('./artifacts/artifact')):
            continue
        jar = product / 'plugins' / (identifier + '_' + release + '.jar')
        directory = jar.with_suffix('')
        if not jar.is_file() and directory.is_dir():
            with zipfile.ZipFile(jar, 'w', zipfile.ZIP_DEFLATED) as archive:
                for source in directory.rglob('*'):
                    if source.is_file():
                        if not source.resolve().is_relative_to(directory.resolve()): raise ValueError('Bundle file escapes disposable product')
                        archive.write(source, source.relative_to(directory).as_posix())
            descriptor = artifact_entries.get((identifier, release))
            if descriptor is not None:
                properties = descriptor.find('properties')
                if properties is not None:
                    for property_entry in list(properties):
                        if property_entry.get('name') in {'download.size', 'artifact.size'}:
                            property_entry.set('value', str(jar.stat().st_size))
                        elif 'checksum' in property_entry.get('name', '') or property_entry.get('name') in {'download.md5', 'artifact.md5'}:
                            properties.remove(property_entry)
                    properties.set('size', str(len(properties)))
        if not jar.is_file():
            continue
        repository_units.append(copy.deepcopy(unit))
        available[identifier] = release
    repository_units.set('size', str(len(repository_units)))
    expected = available.get('org.polarsys.capella.core.data.gen', '')
    if not expected.startswith(version + '.'):
        raise ValueError('Product version mismatch')
    if 'com.google.gson' not in available:
        raise ValueError('Install the MCP feature and its Gson dependency in the disposable copy first')
    metadata = ET.tostring(repository, encoding='utf-8', xml_declaration=True)
    (product / 'content.xml').write_bytes(metadata)
    artifacts.write(product / 'artifacts.xml', encoding='utf-8', xml_declaration=True)
    (product / 'p2.index').write_text('version=1\nmetadata.repository.factory.order=content.xml,!\nartifact.repository.factory.order=artifacts.xml,!\n')
    target = ET.Element('target', name='Independent MCP Capella ' + version, sequenceNumber='1')
    locations = ET.SubElement(target, 'locations')
    location = ET.SubElement(locations, 'location', type='InstallableUnit', includeMode='planner',
        includeAllPlatforms='false', includeSource='false', includeConfigurePhase='false')
    identifiers = ['org.polarsys.capella.core.data.gen', 'org.polarsys.capella.core.model.helpers',
        'org.eclipse.core.runtime', 'org.eclipse.emf.ecore', 'org.eclipse.emf.transaction',
        'org.eclipse.emf.validation', 'org.eclipse.sirius', 'org.eclipse.sirius.diagram', 'org.eclipse.sirius.ui',
        'org.eclipse.gmf.runtime.diagram.ui', 'org.eclipse.gmf.runtime.notation', 'org.eclipse.swt',
        'org.eclipse.ui', 'org.eclipse.jface', 'com.google.gson']
    for identifier in identifiers:
        ET.SubElement(location, 'unit', id=identifier, version=available[identifier])
    ET.SubElement(location, 'repository', location=product.as_uri() + '/')
    output.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(target).write(output, encoding='utf-8', xml_declaration=True)
    print('Generated exact ' + version + ' target from ' + str(len(repository_units)) + ' disposable product bundles:', output)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--product', type=Path, required=True)
    parser.add_argument('--target', type=Path, required=True)
    parser.add_argument('--version', choices=['7.0.1', '7.1.0'], required=True)
    arguments = parser.parse_args()
    generate(arguments.product, arguments.target, arguments.version)
