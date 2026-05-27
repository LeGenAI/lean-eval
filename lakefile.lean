import Lake
open Lake DSL

package LeanEval where

require mathlib from git
  "https://github.com/leanprover-community/mathlib4" @ "master"

@[default_target]
lean_lib LeanEval where
  srcDir := "lean"

require repl from git
  "https://github.com/leanprover-community/repl" @ "master"
