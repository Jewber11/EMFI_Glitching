export interface AssemblyInstruction {
  pc: number;
  bytes_hex: string;
  mnemonic: string;
  operands: string;
  source_file?: string | null;
  source_line?: number | null;
  function?: string | null;
}

export interface AssemblyListing {
  project_id: string;
  build_sha: string;
  cpu_mhz: number;
  instructions: AssemblyInstruction[];
}

export interface Project {
  id: string;
  name: string;
  language: 'c' | 'rust';
  target: string;
  hal: 'ti' | 'b01lers';
  created_at: string;
  description?: string | null;
  build_command?: string | null;
  artifact_elf?: string | null;
  versions: string[];
}

export interface BuildArtifact {
  project_id: string;
  version?: string | null;
  sha: string;
  built_at: string;
  elf_path: string;
  bin_path: string;
  listing_path: string;
  symbols_path: string;
  success: boolean;
  log_tail?: string | null;
  host_script_path?: string | null;
}

export interface GlitchTarget {
  pc_address: number;
  pc_end?: number | null;
  name: string;
  expected_delay_cycles?: number | null;
  expected_delay_cycles_end?: number | null;
  notes?: string | null;
  created_at: string;
}

export interface WsEvent {
  type: string;
  topic?: string | null;
  payload?: Record<string, unknown> | null;
  id?: string | null;
  error?: string | null;
}

export interface FileTreeNode {
  name: string;
  type: 'file' | 'dir';
  path: string;
  children?: FileTreeNode[];
}

export interface Template {
  id: string;
  language: string;
  hal: string;
}

export interface GitLogEntry {
  sha: string;
  message: string;
  date: string;
  author: string;
}
