package io.temporal.nexusjobs.activities;

import io.temporal.activity.ActivityInterface;
import io.temporal.activity.ActivityMethod;
import io.temporal.nexusjobs.model.Todo;

/**
 * The activity behind the workflow-backed Nexus operation.
 *
 * <p>Only the async path uses this. The sync operation calls the same underlying
 * {@link io.temporal.nexusjobs.todo.TodoApi} directly — a sync handler is ordinary code, with no
 * workflow to schedule an activity from.
 */
@ActivityInterface
public interface TodoActivities {

  @ActivityMethod
  Todo fetchTodo(int id);
}
