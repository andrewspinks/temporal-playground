package io.temporal.nexusjobs.todo;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.temporal.nexusjobs.model.Todo;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/** Calls the public jsonplaceholder mock API. No auth, responds in ~300ms. */
public class TodoApiClient implements TodoApi {

  private static final Logger log = LoggerFactory.getLogger(TodoApiClient.class);
  private static final String BASE = "https://jsonplaceholder.typicode.com";

  private final HttpClient http =
      HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(5)).build();
  private final ObjectMapper mapper = new ObjectMapper();

  @Override
  public Todo fetch(int id) {
    String url = BASE + "/todos/" + id;
    log.info("GET {}", url);

    HttpResponse<String> response;
    try {
      response =
          http.send(
              HttpRequest.newBuilder(URI.create(url))
                  .timeout(Duration.ofSeconds(5))
                  .header("accept", "application/json")
                  .GET()
                  .build(),
              HttpResponse.BodyHandlers.ofString());
    } catch (Exception e) {
      throw new Unavailable("GET " + url + " failed", e);
    }

    int status = response.statusCode();
    // jsonplaceholder answers 404 for a nonexistent id, e.g. /todos/9999.
    if (status >= 400 && status < 500) {
      throw new NotFound("todo " + id + " -> HTTP " + status);
    }
    if (status >= 500) {
      throw new Unavailable("todo " + id + " -> HTTP " + status);
    }

    try {
      Todo todo = mapper.readValue(response.body(), Todo.class);
      log.info("fetched {}", todo);
      return todo;
    } catch (Exception e) {
      throw new Malformed("could not parse response for todo " + id, e);
    }
  }
}
