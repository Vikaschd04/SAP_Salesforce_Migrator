"""Platform adapters. One module per side of a pipeline.

An adapter owns *dispatch*, never logic. Every one of these delegates to the same stage
functions the v1 path calls directly — which is what lets the golden harness assert that
running a migration through the adapters produces byte-identical output. An adapter that
reimplemented a stage would be a second copy to keep correct, and there would then be two
answers to "what does this product do".
"""
