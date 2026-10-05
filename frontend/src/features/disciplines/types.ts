export interface Discipline {
  id: string;
  name: string;
  description: string | null;
  academic_year: string | null;
  is_archived: boolean;
  created_at: string;
  updated_at: string;
}

export interface DisciplineInput {
  name: string;
  description: string | null;
  academic_year: string | null;
  group_ids: string[];
}

export interface DisciplineGroup {
  id: string;
  name: string;
  academic_year: string | null;
}

export interface Topic {
  id: string;
  discipline_id: string;
  title: string;
  description: string | null;
  learning_goal: string | null;
  position: number;
  is_archived: boolean;
  created_at: string;
  updated_at: string;
}

export interface TopicInput {
  title: string;
  description: string | null;
  learning_goal: string | null;
  position?: number;
}

export interface TeachingMaterial {
  id: string;
  discipline_id: string;
  topic_id: string;
  title: string;
  original_filename: string;
  content_type: string;
  size_bytes: number;
  sha256: string;
  created_at: string;
}
