// Command gen_descriptors emits a self-contained, topologically-ordered
// FileDescriptorSet covering the server-internal worker-deployment protos
// (WorkerDeploymentWorkflowArgs / WorkerDeploymentVersionWorkflowArgs) and all
// of their transitive imports.
//
// It reads descriptors straight from the Go proto registry (every generated
// .pb.go registers its FileDescriptor at init), so it needs NO .proto sources —
// which matters because the go.temporal.io/api module does not ship them.
//
// This is a one-time build helper. It must be run inside the
// temporal-auto-scaled-workers Go module (so the server proto packages resolve).
// gen_descriptors.sh wires that up and drops the output next to this file.
//
// Usage: go run gen_descriptors.go > deployment_descriptors.binpb
package main

import (
	"os"

	// Importing the server deployment package registers its FileDescriptor and,
	// transitively, every api/common/compute/enums/deployment dependency.
	_ "go.temporal.io/server/api/deployment/v1"

	"google.golang.org/protobuf/proto"
	"google.golang.org/protobuf/reflect/protodesc"
	"google.golang.org/protobuf/reflect/protoreflect"
	"google.golang.org/protobuf/reflect/protoregistry"
	"google.golang.org/protobuf/types/descriptorpb"
)

// The root file that declares both wrapper messages we need to decode.
const rootFile = "temporal/server/api/deployment/v1/message.proto"

func main() {
	root, err := protoregistry.GlobalFiles.FindFileByPath(rootFile)
	if err != nil {
		panic(err)
	}

	var set descriptorpb.FileDescriptorSet
	seen := map[string]bool{}

	// Post-order DFS: emit each file only after all of its imports, so the
	// resulting set can be fed to a Python descriptor_pool in order.
	var visit func(fd protoreflect.FileDescriptor)
	visit = func(fd protoreflect.FileDescriptor) {
		if seen[fd.Path()] {
			return
		}
		seen[fd.Path()] = true
		imports := fd.Imports()
		for i := 0; i < imports.Len(); i++ {
			visit(imports.Get(i).FileDescriptor)
		}
		set.File = append(set.File, protodesc.ToFileDescriptorProto(fd))
	}
	visit(root)

	out, err := proto.Marshal(&set)
	if err != nil {
		panic(err)
	}
	if _, err := os.Stdout.Write(out); err != nil {
		panic(err)
	}
}
