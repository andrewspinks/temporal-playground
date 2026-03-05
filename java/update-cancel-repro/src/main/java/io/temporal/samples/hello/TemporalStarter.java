package io.temporal.samples.hello;

import io.temporal.client.WorkflowClient;
import io.temporal.client.WorkflowClientOptions;
import io.temporal.serviceclient.WorkflowServiceStubs;
import io.temporal.serviceclient.WorkflowServiceStubsOptions;

public class TemporalStarter {

    /** Auto-detects: uses cloud if TEMPORAL_ADDRESS is set, otherwise local dev server. */
    public static WorkflowClient createClient() {
        String address = System.getenv("TEMPORAL_ADDRESS");
        return (address != null && !address.isBlank()) ? createCloudClient() : createLocalClient();
    }

    public static WorkflowClient createLocalClient() {
        WorkflowServiceStubs service = WorkflowServiceStubs.newLocalServiceStubs();
        return WorkflowClient.newInstance(service);
    }

    public static WorkflowClient createCloudClient() {
        String address = requireEnv("TEMPORAL_ADDRESS");
        String namespace = requireEnv("TEMPORAL_NAMESPACE");
        String apiKey = requireEnv("TEMPORAL_API_KEY");

        WorkflowServiceStubs service = WorkflowServiceStubs.newServiceStubs(
                WorkflowServiceStubsOptions.newBuilder()
                        .addApiKey(() -> apiKey)
                        .setTarget(address)
                        .setEnableHttps(true)
                        .build());

        return WorkflowClient.newInstance(
                service,
                WorkflowClientOptions.newBuilder()
                        .setNamespace(namespace)
                        .build());
    }

    private static String requireEnv(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException("Required environment variable not set: " + name);
        }
        return value;
    }
}
