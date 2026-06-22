# frozen_string_literal: true

require 'logger'
require 'temporalio/client'
require 'temporalio/worker'
require_relative 'fanout'

$stdout.sync = true

task_queue = ENV.fetch('TQ')
cache      = Integer(ENV.fetch('CACHE', '1000'))
gate_hold  = Float(ENV.fetch('GATE_HOLD_S', '0')) # >0: helper holds GATE this long to park batch-0 tail fibers

# Helper holds the workflow's GATE so batch-0 tail fibers park during the first
# activation. Grab it NOW (before any workflow starts), release after gate_hold s.
if gate_hold.positive?
  Fanout::GATE.lock
  puts "GATE held for #{gate_hold}s (parks batch-0 fibers >= #{Fanout::PARK_FROM})"
  Thread.new do
    sleep(gate_hold)
    Fanout::GATE.unlock
    puts 'GATE released'
  end
end

client = Temporalio::Client.connect('localhost:7233', 'default',
                                    logger: Logger.new($stdout, level: Logger::WARN))
worker = Temporalio::Worker.new(
  client:, task_queue:,
  workflows: [Fanout::Fanout], activities: [Fanout::LeafActivity],
  max_cached_workflows: cache
)
puts "WORKER UP tq=#{task_queue} cache=#{cache} pid=#{Process.pid}"
worker.run(shutdown_signals: ['SIGINT', 'SIGTERM'])
