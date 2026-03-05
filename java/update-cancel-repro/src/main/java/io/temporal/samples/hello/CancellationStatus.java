package io.temporal.samples.hello;

/** Result type returned by the checkCancellation update handler. */
public class CancellationStatus {
  private boolean cancelled;
  private String reason;

  // Required for Temporal's Jackson serialization
  public CancellationStatus() {}

  private CancellationStatus(boolean cancelled, String reason) {
    this.cancelled = cancelled;
    this.reason = reason;
  }

  public static CancellationStatus cancelled(String reason) {
    return new CancellationStatus(true, reason);
  }

  public static CancellationStatus notCancelled() {
    return new CancellationStatus(false, null);
  }

  public boolean isCancelled() {
    return cancelled;
  }

  public void setCancelled(boolean cancelled) {
    this.cancelled = cancelled;
  }

  public String getReason() {
    return reason;
  }

  public void setReason(String reason) {
    this.reason = reason;
  }

  @Override
  public String toString() {
    return "CancellationStatus{cancelled=" + cancelled + ", reason='" + reason + "'}";
  }
}
