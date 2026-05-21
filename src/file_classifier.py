"""
File Classifier - Shared utilities for classifying source files (test vs code, generated vs source).
Used by both GitHubClient and GitLabClient for LOC report split_test feature.
"""


def is_test_file(filepath: str) -> bool:
    """Check if a file path is a test file (supports Python, JS/TS/React/ReactNative, Java/Spring Boot, Go, .NET)"""
    fp = filepath.lower()
    # Test directories
    test_dirs = [
        '__tests__/', '/test/', '/tests/', '__mocks__/', '__snapshots__/', '/spec/',
        '/src/test/', '/src/it/',  # Java Maven/Gradle conventional test directories
        '/test-utils/', '/testing/', '/testdata/',
        '/e2e/',  # React Native (Detox) e2e tests
        '.tests/', '.test/', '.unittests/', '.integrationtests/',  # .NET test project conventions
    ]
    for d in test_dirs:
        if d in fp:
            return True

    filename = fp.rsplit('/', 1)[-1]

    # JavaScript / TypeScript / React test files
    js_test_suffixes = (
        '.test.ts', '.test.tsx', '.test.js', '.test.jsx',
        '.spec.ts', '.spec.tsx', '.spec.js', '.spec.jsx',
        '.stories.tsx', '.stories.ts', '.stories.js',  # Storybook
    )
    for suffix in js_test_suffixes:
        if filename.endswith(suffix):
            return True

    # Python test files
    if filename.endswith('_test.py') or filename.startswith('test_') and filename.endswith('.py'):
        return True
    if filename == 'conftest.py':
        return True

    # Java / Spring Boot test files
    if filename.endswith('.java'):
        name_no_ext = filename[:-5]
        if name_no_ext.endswith('test') or name_no_ext.endswith('tests'):
            return True
        if name_no_ext.endswith('it') and len(name_no_ext) > 2:  # integration test
            return True
        if name_no_ext.endswith('spec'):
            return True
        if name_no_ext.startswith('test'):
            return True

    # Go test files
    if filename.endswith('_test.go'):
        return True

    # .NET (C#, F#, VB.NET) test files
    if filename.endswith('.cs') or filename.endswith('.fs') or filename.endswith('.vb'):
        ext_len = 3 if filename.endswith('.cs') or filename.endswith('.fs') or filename.endswith('.vb') else 0
        name_no_ext = filename[:-ext_len] if ext_len else filename
        # xUnit / NUnit / MSTest naming conventions
        if name_no_ext.endswith('tests') or name_no_ext.endswith('test'):
            return True
        if name_no_ext.endswith('spec'):
            return True
        if name_no_ext.startswith('test'):
            return True
        # Common patterns: MyClassTests.cs, MyClass_Tests.cs
        if '_tests' in name_no_ext or '_test' in name_no_ext:
            return True

    # Jest setup / test config
    test_config_files = (
        'jest.config.js', 'jest.config.ts', 'jest.setup.js', 'jest.setup.ts',
        'setuptests.ts', 'setuptest.ts', 'setuptest.js', 'setuptests.ts',
    )
    if filename.lower() in test_config_files:
        return True

    return False


def is_generated_or_non_source(filepath: str) -> bool:
    """Check if a file should be excluded from LOC count (generated, configs, assets, lock files)"""
    fp = filepath.lower()
    filename = fp.rsplit('/', 1)[-1]

    # Lock files and dependency manifests that shouldn't count
    excluded_files = {
        'package-lock.json', 'yarn.lock', 'pnpm-lock.yaml',
        'composer.lock', 'gemfile.lock', 'poetry.lock', 'pipfile.lock',
        'gradle.lockfile', '.gradle', 'gradlew', 'gradlew.bat',
        'mvnw', 'mvnw.cmd',
        # .NET
        'packages.lock.json', 'global.json',
    }
    if filename in excluded_files:
        return True

    # Generated/build directories
    generated_dirs = [
        'node_modules/', 'dist/', 'build/', 'target/', 'out/',
        '.gradle/', '.mvn/', 'generated/', 'generated-sources/',
        '.next/', 'coverage/', '.nyc_output/',
        'vendor/', '__generated__/',
        # React Native
        '.expo/', 'ios/pods/', 'ios/build/',
        'android/build/', 'android/app/build/',
        # .NET
        'bin/', 'obj/', 'packages/', '.vs/',
        'testresults/', 'artifacts/',
    ]
    for d in generated_dirs:
        if fp.startswith(d) or ('/' + d) in fp:
            return True

    # Non-source file extensions (binary, assets, configs)
    non_source_ext = (
        '.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico', '.webp', '.bmp',
        '.woff', '.woff2', '.ttf', '.eot', '.otf',
        '.pdf', '.zip', '.tar', '.gz', '.jar', '.war', '.class',
        '.min.js', '.min.css', '.map',
        '.lock',
        # React Native / mobile binaries
        '.apk', '.aab', '.ipa', '.so', '.dex',
        # .NET binaries and generated
        '.dll', '.exe', '.pdb', '.nupkg', '.snupkg',
        '.designer.cs', '.g.cs', '.g.i.cs',
    )
    for ext in non_source_ext:
        if fp.endswith(ext):
            return True

    return False
