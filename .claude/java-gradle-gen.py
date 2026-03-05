#!/usr/bin/env python3
"""Generate build.gradle and settings.gradle for a scaffolded Java Temporal project."""
import sys

project_dir = sys.argv[1]
base = sys.argv[2]
sdk_version = sys.argv[3]
sample = sys.argv[4]

with open(f"{project_dir}/settings.gradle", "w") as f:
    f.write(f"rootProject.name = '{base}'\n")

with open(f"{project_dir}/build.gradle", "w") as f:
    f.write(f"""\
plugins {{
    id 'java'
    id 'application'
}}

sourceCompatibility = '11'
targetCompatibility = '11'

repositories {{
    mavenCentral()
}}

dependencies {{
    implementation 'io.temporal:temporal-sdk:{sdk_version}'
    implementation 'io.temporal:temporal-envconfig:{sdk_version}'
    testImplementation 'io.temporal:temporal-testing:{sdk_version}'

    implementation platform('com.fasterxml.jackson:jackson-bom:2.17.2')
    implementation 'com.fasterxml.jackson.core:jackson-databind'
    implementation 'com.fasterxml.jackson.core:jackson-core'

    implementation 'ch.qos.logback:logback-classic:1.5.6'

    testImplementation 'junit:junit:4.13.2'
    testImplementation 'org.mockito:mockito-core:5.12.0'
}}

application {{
    mainClass = project.properties['mainClass'] ?: 'io.temporal.samples.{sample}.Starter'
}}

tasks.named('run') {{
    standardInput = System.in
}}
""")
