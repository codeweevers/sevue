#!/usr/bin/env python3
import subprocess, sys, re

if len(sys.argv) < 2:
    print("Usage: python release.py <version>")
    sys.exit(1)

version = sys.argv[1]

# Build number = number of commits
build_number = subprocess.check_output(['git', 'rev-list', '--count', 'HEAD']).decode().strip()

# Update pubspec.yaml
with open('pubspec.yaml') as f:
    data = f.read()

data = re.sub(r'^version: .*', f'version: {version}+{build_number}', data, flags=re.M)
with open('pubspec.yaml', 'w') as f:
    f.write(data)

# Commit, tag, push
subprocess.run(f'git add pubspec.yaml && git commit -m "Bump version to {version}+{build_number}"', shell=True, check=True)
subprocess.run(f'git tag -a v{version} -m "Release v{version}"', shell=True, check=True)
subprocess.run(f'git push origin HEAD && git push origin v{version}', shell=True, check=True)

print(f"Version bumped and tagged as v{version}+{build_number}")
