package io.temporal.nexusjobs.model;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;

/**
 * A todo from jsonplaceholder.typicode.com.
 *
 * <p>Jackson deserializes this twice over: once from the HTTP response body, and again by the SDK's
 * DataConverter when it crosses an activity / Nexus / workflow boundary.
 */
@JsonIgnoreProperties(ignoreUnknown = true)
public class Todo {
  private final int userId;
  private final int id;
  private final String title;
  private final boolean completed;

  @JsonCreator(mode = JsonCreator.Mode.PROPERTIES)
  public Todo(
      @JsonProperty("userId") int userId,
      @JsonProperty("id") int id,
      @JsonProperty("title") String title,
      @JsonProperty("completed") boolean completed) {
    this.userId = userId;
    this.id = id;
    this.title = title;
    this.completed = completed;
  }

  @JsonProperty("userId")
  public int getUserId() {
    return userId;
  }

  @JsonProperty("id")
  public int getId() {
    return id;
  }

  @JsonProperty("title")
  public String getTitle() {
    return title;
  }

  @JsonProperty("completed")
  public boolean isCompleted() {
    return completed;
  }

  @Override
  public String toString() {
    return String.format(
        "Todo{userId=%d, id=%d, title='%s', completed=%s}", userId, id, title, completed);
  }
}
