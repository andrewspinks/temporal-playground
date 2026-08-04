package io.temporal.nexusjobs.service;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonProperty;

/** Input to both JobService operations. */
public class TodoRequest {
  private final int id;

  @JsonCreator(mode = JsonCreator.Mode.PROPERTIES)
  public TodoRequest(@JsonProperty("id") int id) {
    this.id = id;
  }

  @JsonProperty("id")
  public int getId() {
    return id;
  }

  @Override
  public String toString() {
    return "TodoRequest{id=" + id + "}";
  }
}
