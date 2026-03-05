# Temporal Playground — Task Runner

# Dev server ─────────────────────────────────────────────

# Start Temporal dev server
server:
    temporal server start-dev

# Start Temporal dev server with UI on port 8080
server-ui:
    temporal server start-dev --ui-port 8080

# Setup ──────────────────────────────────────────────────

# Install all toolchain dependencies via mise
setup:
    mise install

# Print installed tool versions
versions:
    @echo "just     $(just --version)"
    @echo "go       $(go version)"
    @echo "node     $(node --version)"
    @echo "python   $(python --version)"
    @echo "java     $(java --version 2>&1 | head -1)"
    @echo "dotnet   $(dotnet --version)"
    @echo "temporal $(temporal --version)"
    @echo "uv       $(uv --version)"
    @echo "pnpm     $(pnpm --version)"
    @echo "ruby     $(ruby --version)"
    @echo "gradle   $(gradle --version | grep Gradle)"

# History export & replay ──────────────────────────────

# Default connection settings (override with `just --set namespace prod ...`)
namespace := "default"
address := "localhost:7233"

# Export workflow history as JSON
history-export workflow-id run-id="":
    #!/usr/bin/env bash
    set -euo pipefail
    mkdir -p histories
    args=(--workflow-id "{{workflow-id}}" --namespace "{{namespace}}" --address "{{address}}" --output json)
    if [ -n "{{run-id}}" ]; then
        args+=(--run-id "{{run-id}}")
    fi
    out="histories/{{workflow-id}}.json"
    temporal workflow show "${args[@]}" > "$out"
    echo "Exported to $out"

# Replay a workflow from a saved history file
history-replay file:
    temporal workflow replay --file "{{file}}" --namespace "{{namespace}}" --address "{{address}}"

# List saved history files
history-list:
    @ls -1 histories/*.json 2>/dev/null || echo "No history files found in histories/"

# Scaffolding ────────────────────────────────────────────

# Private helper: clone or update a Temporal samples repo into .cache/samples-{lang}/
_clone-samples lang:
    #!/usr/bin/env bash
    set -euo pipefail
    CACHE_DIR=".cache/samples-{{lang}}"
    REPO_URL="https://github.com/temporalio/samples-{{lang}}.git"
    if [ -d "$CACHE_DIR/.git" ]; then
        echo "Updating samples-{{lang}} cache..."
        git -C "$CACHE_DIR" fetch --depth 1 origin main --quiet
        git -C "$CACHE_DIR" checkout FETCH_HEAD --quiet
    else
        echo "Cloning samples-{{lang}} (shallow)..."
        mkdir -p "$(dirname "$CACHE_DIR")"
        git clone --depth 1 --branch main "$REPO_URL" "$CACHE_DIR"
    fi

# Scaffold a new TypeScript project from temporalio/samples-typescript
# Usage: just new-ts sample=hello-world [name=my-project]
# If name is omitted, defaults to the sample name. Auto-increments if directory already exists.
new-ts sample="hello-world" name="":
    #!/usr/bin/env bash
    set -euo pipefail
    CACHE_DIR=".cache/samples-typescript"

    just _clone-samples typescript

    # Validate sample exists
    if [ ! -d "$CACHE_DIR/{{sample}}" ]; then
        echo "Error: sample '{{sample}}' not found in samples-typescript." >&2
        echo ""
        echo "Available samples:"
        for d in "$CACHE_DIR"/*/; do
            [ -f "${d}package.json" ] && basename "$d"
        done | sort
        exit 1
    fi

    # Resolve unique project directory name under ts/
    BASE="{{name}}"
    if [ -z "$BASE" ]; then
        BASE="{{sample}}"
    fi
    PROJECT_DIR="ts/${BASE}"
    SUFFIX=2
    while [ -d "$PROJECT_DIR" ]; do
        PROJECT_DIR="ts/${BASE}-${SUFFIX}"
        SUFFIX=$((SUFFIX + 1))
    done
    if [ "$PROJECT_DIR" != "ts/${BASE}" ]; then
        echo "Directory 'ts/${BASE}' already exists; using '$PROJECT_DIR' instead."
    fi

    # Copy sample into project directory
    echo "Creating project '$PROJECT_DIR' from sample '{{sample}}'..."
    cp -r "$CACHE_DIR/{{sample}}" "$PROJECT_DIR"

    # Remove repo-specific scaffolding files
    rm -f "$PROJECT_DIR/.post-create" "$PROJECT_DIR/.nvmrc" "$PROJECT_DIR/.npmrc"

    # Update package name in package.json
    if [ -f "$PROJECT_DIR/package.json" ]; then
        node -e "
          const fs = require('fs');
          const pkg = JSON.parse(fs.readFileSync('${PROJECT_DIR}/package.json', 'utf8'));
          pkg.name = '${PROJECT_DIR}';
          fs.writeFileSync('${PROJECT_DIR}/package.json', JSON.stringify(pkg, null, 2) + '\n');
        "
    fi

    # Install dependencies
    echo "Installing dependencies with pnpm..."
    (cd "$PROJECT_DIR" && pnpm install)

    echo ""
    echo "Project '$PROJECT_DIR' ready. Next steps:"
    echo "  cd $PROJECT_DIR"
    echo "  just server          # start Temporal dev server (in a separate terminal)"
    echo "  pnpm run start       # start the Worker"
    echo "  pnpm run workflow    # run the Workflow client"
    if [ -f "$PROJECT_DIR/README.md" ]; then
        echo ""
        echo "See $PROJECT_DIR/README.md for sample-specific instructions."
    fi

# Scaffold a new Python project
new-py name="hello":
    @echo "TODO: scaffold Python project '{{name}}'"

# Scaffold a new Java project from temporalio/samples-java
# Usage: just new-java <sample> [<project-name>]
# If project-name is omitted, defaults to sample name. Auto-increments if directory exists.
new-java sample="hello" name="":
    #!/usr/bin/env bash
    set -euo pipefail
    CACHE_DIR=".cache/samples-java"
    SAMPLES_PKG="$CACHE_DIR/core/src/main/java/io/temporal/samples"

    just _clone-samples java

    # Validate sample exists
    if [ ! -d "$SAMPLES_PKG/{{sample}}" ]; then
        echo "Error: sample '{{sample}}' not found in samples-java." >&2
        echo ""
        echo "Available samples:"
        for d in "$SAMPLES_PKG"/*/; do
            basename "$d"
        done | sort
        exit 1
    fi

    # Resolve unique project directory name under java/
    BASE="{{name}}"
    if [ -z "$BASE" ]; then
        BASE="{{sample}}"
    fi
    PROJECT_DIR="java/${BASE}"
    SUFFIX=2
    while [ -d "$PROJECT_DIR" ]; do
        PROJECT_DIR="java/${BASE}-${SUFFIX}"
        SUFFIX=$((SUFFIX + 1))
    done
    if [ "$PROJECT_DIR" != "java/${BASE}" ]; then
        echo "Directory 'java/${BASE}' already exists; using '$PROJECT_DIR' instead."
    fi

    # Extract SDK version from samples repo
    SDK_VERSION=$(grep -o "javaSDKVersion = '[^']*'" "$CACHE_DIR/build.gradle" | grep -o "'[^']*'" | tr -d "'" || echo "1.32.1")
    echo "Using Temporal Java SDK version: $SDK_VERSION"

    # Create project directory structure
    mkdir -p "$PROJECT_DIR/src/main/java/io/temporal/samples"
    mkdir -p "$PROJECT_DIR/src/test/java/io/temporal/samples"

    # Copy sample package
    echo "Copying sample '{{sample}}'..."
    cp -r "$SAMPLES_PKG/{{sample}}" "$PROJECT_DIR/src/main/java/io/temporal/samples/"

    # Copy common package (most samples depend on it)
    if [ -d "$SAMPLES_PKG/common" ]; then
        cp -r "$SAMPLES_PKG/common" "$PROJECT_DIR/src/main/java/io/temporal/samples/"
    fi

    # Copy Gradle wrapper from samples repo
    cp "$CACHE_DIR/gradlew" "$PROJECT_DIR/gradlew"
    cp "$CACHE_DIR/gradlew.bat" "$PROJECT_DIR/gradlew.bat"
    cp -r "$CACHE_DIR/gradle" "$PROJECT_DIR/gradle"
    chmod +x "$PROJECT_DIR/gradlew"

    # Generate settings.gradle and build.gradle via helper script (avoids just heredoc parser issues with dots)
    python3 .claude/java-gradle-gen.py "$PROJECT_DIR" "$BASE" "$SDK_VERSION" "{{sample}}"

    echo ""
    echo "Project '$PROJECT_DIR' ready. Next steps:"
    echo "  cd $PROJECT_DIR"
    echo "  just server          # start Temporal dev server (in a separate terminal)"
    echo "  ./gradlew run -PmainClass=io.temporal.samples.{{sample}}.<MainClass>"
    echo ""
    echo "Replace <MainClass> with the entry point in src/main/java/io/temporal/samples/{{sample}}/"
    ls "$PROJECT_DIR/src/main/java/io/temporal/samples/{{sample}}/"*.java 2>/dev/null | xargs -I{} basename {} .java | sort | sed 's/^/  - /'

# Scaffold a new Ruby project
new-ruby name="hello":
    @echo "TODO: scaffold Ruby project '{{name}}'"

# Scaffold a new .NET project
new-dotnet name="hello":
    @echo "TODO: scaffold .NET project '{{name}}'"
