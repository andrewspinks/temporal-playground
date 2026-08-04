package io.temporal.nexusjobs.todo;

import io.temporal.nexusjobs.model.Todo;

/**
 * The work the Nexus service actually does, with no Temporal types in sight.
 *
 * <p>Both operations go through this: the sync operation calls it directly, and the workflow-backed
 * operation calls it from inside an activity. Keeping it framework-neutral is what lets each side map
 * the same failures onto its own error model — a Nexus {@code HandlerException} for the sync
 * operation, an {@code ApplicationFailure} for the activity.
 *
 * <p>An interface (rather than just the impl) so a handler test can substitute a fake.
 */
public interface TodoApi {

  Todo fetch(int id);

  /** The id does not exist — a 4xx. Retrying cannot help. */
  class NotFound extends RuntimeException {
    public NotFound(String message) {
      super(message);
    }
  }

  /** Upstream is unhealthy or unreachable — a 5xx or transport error. Worth retrying. */
  class Unavailable extends RuntimeException {
    public Unavailable(String message, Throwable cause) {
      super(message, cause);
    }

    public Unavailable(String message) {
      super(message);
    }
  }

  /** A 2xx whose body could not be parsed. Retrying will not fix it. */
  class Malformed extends RuntimeException {
    public Malformed(String message, Throwable cause) {
      super(message, cause);
    }
  }
}
