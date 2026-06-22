# frozen_string_literal: true

require 'temporalio/activity'
require 'temporalio/workflow'

# Deterministic demonstration of the PARK → partial-commit mechanism.
#
# https://github.com/protocolbuffers/protobuf/blob/v31.1/ruby/lib/google/protobuf/internal/object_cache.rb#L34-L37
#
module Fanout
  BATCH = 100
  DELAY = 1
  PARK_FROM = 65 # batch-0 fibers >= this index park (committed batch becomes 65)
  GATE = Mutex.new

  class LeafActivity < Temporalio::Activity::Definition
    def execute(_arg)
      'ok'
    end
  end

  class Fanout < Temporalio::Workflow::Definition
    workflow_name 'Fanout'

    def execute(total)
      futures = []
      (0...total).to_a.each_slice(BATCH).with_index do |batch, batch_idx|
        Temporalio::Workflow.sleep(DELAY) if batch_idx.positive?
        batch.each_with_index do |i, j|
          futures << Temporalio::Workflow::Future.new do
            # Park only batch-0's tail fibers, only while the helper holds GATE.
            # On replay (no helper) this synchronize is uncontended → no park.
            if batch_idx.zero? && j >= PARK_FROM
              Temporalio::Workflow::Unsafe.illegal_call_tracing_disabled { GATE.synchronize { nil } }
            end
            Temporalio::Workflow.execute_activity(LeafActivity, i, start_to_close_timeout: 120)
          end
        end
      end
      Temporalio::Workflow::Future.all_of(*futures).wait
      futures.size
    end
  end
end
