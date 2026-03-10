# (1,N) Regular Register Implementation

## Phase 1: Basic Implementation
- [x] Implement WriterProcess and ReaderProcess in register.py
- [x] Create main.py to simulate the scenario
- [x] Run simulation and verify results
- [x] Create this todo.md file

## Phase 2: Majority-Based Approach
- [x] Upgrade RegisterValue to include timestamps
- [x] Implement ReplicaProcess for storing values with timestamp comparison
- [x] Upgrade WriterProcess to use majority quorum for writes
- [x] Upgrade ReaderProcess to broadcast read requests and collect majority responses
- [x] Update main.py for 5-process cluster scenario
- [x] Print timestamps alongside values for verification

## Phase 3: Atomic Register (Two-Phase Read)
- [x] Upgrade ReaderProcess with two-phase read protocol
  - Phase 1: Broadcast READ_REQ, collect majority responses, pick highest timestamp
  - Phase 2: Write-back highest value to all replicas, wait for majority ACKs
- [x] Add get_phase() method for debugging/logging
- [x] Update main.py for 3 concurrent readers scenario
- [x] Print phase information showing write-back completion
- [x] Verify atomicity: later reads never return older values

## Phase 4: Multi-Writer Atomic Register
- [x] Create Timestamp class with writer ID for unique ordering
- [x] Replace WriterProcess, ReaderProcess, ReplicaProcess with unified RegisterProcess
- [x] Every process stores timestamp-value pair and handles READ/WRITE messages
- [x] Write operation now has two phases:
  - Phase 1: Read current timestamps from majority, pick highest
  - Phase 2: Increment timestamp, broadcast write, wait for majority ACKs
- [x] Update main.py for 3 concurrent writers and 5 readers scenario
- [x] Verify all reads return same value from exactly one writer

## Phase 5: Rich Visualization and Stress Testing
- [x] Add Rich-based visualization with state tables after each operation
- [x] Track participating replicas in majority quorums
- [x] Color coding: green (completed), yellow (participant), red strikethrough (crashed)
- [x] Create stress scenario with 7 processes:
  - Phase 1: 3 concurrent writes
  - Phase 2: 2 concurrent reads while writes in flight
  - Phase 3: Crash 2 processes
  - Phase 4: 2 concurrent writes from remaining processes
  - Phase 5: 2 concurrent reads while writes in flight
  - Phase 6: 5 final concurrent reads
- [x] Print summary with operation counts, quorum sizes, and value verification

## Phase 6: Comprehensive Testing
- [x] Test 1: Non-concurrent read returns last written value
- [x] Test 2: Concurrent read returns only old or new value (never invented)
- [x] Test 3: Atomic reads don't go backwards in time
- [x] Test 4: Concurrent writes result in consistent reads across all processes
- [x] Test 5: Timestamp tiebreak by writer ID is consistent
- [x] Test 6: Majority survives minority crash
- [x] Test 7: Crashed process does not affect correctness
