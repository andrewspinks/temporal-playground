package io.temporal.nexusjobs.caller;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonProperty;
import io.temporal.nexusjobs.model.Todo;

/** Both operations' results side by side, with how long each took from the caller's point of view. */
public class CallerResult {
  private final Todo viaSyncOperation;
  private final Todo viaAsyncOperation;
  private final long syncOpMillis;
  private final long asyncOpMillis;

  @JsonCreator(mode = JsonCreator.Mode.PROPERTIES)
  public CallerResult(
      @JsonProperty("viaSyncOperation") Todo viaSyncOperation,
      @JsonProperty("viaAsyncOperation") Todo viaAsyncOperation,
      @JsonProperty("syncOpMillis") long syncOpMillis,
      @JsonProperty("asyncOpMillis") long asyncOpMillis) {
    this.viaSyncOperation = viaSyncOperation;
    this.viaAsyncOperation = viaAsyncOperation;
    this.syncOpMillis = syncOpMillis;
    this.asyncOpMillis = asyncOpMillis;
  }

  @JsonProperty("viaSyncOperation")
  public Todo getViaSyncOperation() {
    return viaSyncOperation;
  }

  @JsonProperty("viaAsyncOperation")
  public Todo getViaAsyncOperation() {
    return viaAsyncOperation;
  }

  @JsonProperty("syncOpMillis")
  public long getSyncOpMillis() {
    return syncOpMillis;
  }

  @JsonProperty("asyncOpMillis")
  public long getAsyncOpMillis() {
    return asyncOpMillis;
  }
}
