export interface VpnInfo {
  in_use: boolean | null;
  interface: string | null;
  type: string | null;
}

export interface RecentError {
  timestamp: string;
  level: string;
  message: string;
}

export interface InstanceInfo {
  hostname?: string;
  platform?: string;
  cpu_percent?: number;
  memory_percent?: number;
  memory_available_mb?: number;
  disk_percent?: number;
  disk_free_gb?: number;
  processing_streams?: number;
  total_streams?: number;
  distribution_mode?: string;
  static_total_servers?: number;
  cached_active_servers?: number;
  python_version?: string;
  processing_stream_names?: string[];
  vpn?: VpnInfo;
  recent_errors?: RecentError[];
}

export interface Instance {
  server_id: number;
  last_heartbeat: string;
  status: "ONLINE" | "OFFLINE";
  ip_address?: string | null;
  info: InstanceInfo;
}

export interface MusicRecord {
  date: string;
  time: string;
  name: string;
  artist: string;
  song_title: string;
}