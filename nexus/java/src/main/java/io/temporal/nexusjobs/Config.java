package io.temporal.nexusjobs;

import io.temporal.envconfig.ClientConfigProfile;
import io.temporal.envconfig.LoadClientConfigProfileOptions;
import java.io.IOException;

/**
 * Shared names and connection config for the handler and caller programs.
 *
 * <p>The handler side and caller side sit in different namespaces and may live in different Temporal
 * Cloud accounts, so they need <em>separate credentials</em>. That rules out the ambient
 * TEMPORAL_ADDRESS / TEMPORAL_NAMESPACE / TEMPORAL_API_KEY variables — there is only one of each per
 * process environment, and a single API key cannot authenticate to two accounts.
 *
 * <p>Instead each program declares its {@link Role} and loads the matching <b>envconfig profile</b>
 * from a TOML config file, which carries that role's own address, namespace, and api_key. See
 * `temporal.toml.example`. The `temporal` CLI reads the same file and profiles via
 * `--config-file` / `--profile`, so CLI and SDK stay in sync.
 *
 * <p><b>Do not set TEMPORAL_API_KEY, TEMPORAL_ADDRESS, or TEMPORAL_NAMESPACE.</b> envconfig applies
 * env vars <em>on top of</em> the loaded profile, so any of them would override both roles with one
 * value — silently collapsing the two identities back into one.
 */
public final class Config {

  /** Which side of the Nexus call a program is on. Selects its credentials and namespace. */
  public enum Role {
    HANDLER,
    CALLER
  }

  /**
   * Loads the envconfig profile for this role.
   *
   * <p>Profile names come from HANDLER_PROFILE / CALLER_PROFILE (defaults: `handler` / `caller`), so
   * switching between Cloud and a local dev server is a matter of pointing at different profiles
   * rather than editing code.
   *
   * <p>If no config file or no matching profile exists, this falls back to plain env-var config so
   * the local dev-server path keeps working with no TOML at all.
   */
  public static ClientConfigProfile loadProfile(Role role) throws IOException {
    String profileName =
        role == Role.HANDLER ? envOr("HANDLER_PROFILE", "handler") : envOr("CALLER_PROFILE", "caller");
    try {
      return ClientConfigProfile.load(
          LoadClientConfigProfileOptions.newBuilder().setConfigFileProfile(profileName).build());
    } catch (IllegalArgumentException e) {
      // Thrown when the named profile is absent from the config file (or there is no file).
      System.err.printf(
          "No '%s' profile found (%s) — falling back to env-var config.%n",
          profileName, e.getMessage());
      return ClientConfigProfile.load();
    }
  }

  /** The profile's namespace if it declares one, else this role's built-in default. */
  public static String namespaceFor(Role role, ClientConfigProfile profile) {
    String ns = profile.getNamespace();
    if (ns != null && !ns.isEmpty()) {
      return ns;
    }
    return role == Role.HANDLER ? HANDLER_NAMESPACE : CALLER_NAMESPACE;
  }

  /**
   * Fallback handler-side namespace, used only when the loaded profile does not declare one. Prefer
   * putting `namespace` in the profile.
   */
  public static final String HANDLER_NAMESPACE =
      envOr("HANDLER_NAMESPACE", "playground-nexus-handler.yy98u");

  /** Fallback caller-side namespace. A Nexus call is meant to cross a namespace boundary. */
  public static final String CALLER_NAMESPACE =
      envOr("CALLER_NAMESPACE", "playground-nexus-caller.yy98u");

  /**
   * Handler task queue — Nexus, workflow, and activity tasks all land here.
   *
   * <p>Overridable so the collision demo (`just java-collision-demo`) can point this worker at the
   * Python handler's queue without a code change. See NexusHandlerWorker for what goes wrong there.
   */
  public static final String HANDLER_TASK_QUEUE =
      envOr("JAVA_HANDLER_TASK_QUEUE", "java-handler-task-queue");

  /** Workflow task queue for the Java caller worker. */
  public static final String CALLER_TASK_QUEUE = "java-caller-task-queue";

  /** Endpoint targeting HANDLER_NAMESPACE / HANDLER_TASK_QUEUE. */
  public static final String NEXUS_ENDPOINT =
      envOr("JAVA_NEXUS_ENDPOINT", "Nexus-java-endpoint");

  private static String envOr(String name, String fallback) {
    String v = System.getenv(name);
    return (v == null || v.isEmpty()) ? fallback : v;
  }

  private Config() {}
}
