import { httpClient } from './httpClient';
import type { TaskPriority } from '@/utils/taskReview';
import {
  isSimulatorActive,
  simCreateNotification,
  simCreateTask,
  simListNotifications,
  simListTasks,
  simMarkNotificationRead,
  simUpdateTask,
} from '../simulator/simulatorStore';

export type OperationalTaskStatus = 'Assigned' | 'In Progress' | 'Submitted';
export type OperationalTaskSource = 'ai' | 'manual';

export interface ReportPhoto {
  filename: string;
  mimeType: string;
  size: number;
  dataUrl: string;
}

export interface FieldReport {
  at: string;
  byId: string;
  byName: string;
  text: string;
  peopleAssisted: number | null;
  locationNote: string | null;
  photos?: ReportPhoto[];
}

export interface BackendTask {
  id: string;
  title: string;
  department: string;
  location: string;
  priority: TaskPriority;
  assigneeUserId: string;
  assigneeName: string;
  instructions: string;
  deadline: string | null;
  status: OperationalTaskStatus;
  progress: number;
  source: OperationalTaskSource;
  sourceRef: string | null;
  regionKey: string | null;
  createdAt: string;
  createdById: string;
  createdByName: string;
  updatedAt: string;
  reports: FieldReport[];
}

export interface CreateTaskInput {
  title: string;
  department: string;
  location: string;
  priority: TaskPriority;
  assigneeUserId: string;
  instructions?: string;
  deadline?: string | null;
  source?: OperationalTaskSource;
  sourceRef?: string | null;
  regionKey?: string | null;
  notifyAssignee?: boolean;
}

export interface UpdateTaskInput {
  status?: OperationalTaskStatus;
  progress?: number;
  title?: string;
  department?: string;
  location?: string;
  priority?: TaskPriority;
  instructions?: string;
  deadline?: string | null;
  assigneeUserId?: string;
  notifyAssignee?: boolean;
  report?: {
    text: string;
    peopleAssisted?: number | null;
    locationNote?: string | null;
    photos?: ReportPhoto[];
  };
}

export interface OperationalNotification {
  id: string;
  recipientUserId: string;
  recipientName: string;
  senderId: string;
  senderName: string;
  message: string;
  priority: TaskPriority;
  taskId: string | null;
  regionKey: string | null;
  read: boolean;
  createdAt: string;
}

export interface CreateNotificationInput {
  recipientUserId: string;
  message: string;
  priority: TaskPriority;
  taskId?: string | null;
  regionKey?: string | null;
}

interface TaskListResponse {
  success: boolean;
  count: number;
  tasks: BackendTask[];
}

interface TaskResponse {
  success: boolean;
  task: BackendTask;
}

interface NotificationListResponse {
  success: boolean;
  count: number;
  unread: number;
  notifications: OperationalNotification[];
}

interface NotificationResponse {
  success: boolean;
  notification: OperationalNotification;
}

// Simulator Mode: when a drill is active, tasks and notifications are served
// from (and written to) the isolated in-memory drill snapshot. Live paths
// are untouched and run exactly as before when the simulator is off.

export const tasksApi = {
  async list(params?: { assigneeUserId?: string; regionKey?: string; status?: string }): Promise<BackendTask[]> {
    if (isSimulatorActive()) return simListTasks(params);
    const search = new URLSearchParams();
    if (params?.assigneeUserId) search.set('assigneeUserId', params.assigneeUserId);
    if (params?.regionKey) search.set('regionKey', params.regionKey);
    if (params?.status) search.set('status', params.status);
    const suffix = search.toString() ? `?${search.toString()}` : '';
    const result = await httpClient.get<TaskListResponse>(`/tasks${suffix}`);
    return result.tasks ?? [];
  },
  async create(input: CreateTaskInput): Promise<BackendTask> {
    if (isSimulatorActive()) return simCreateTask(input);
    const result = await httpClient.post<TaskResponse, CreateTaskInput>('/tasks', input);
    return result.task;
  },
  async update(taskId: string, input: UpdateTaskInput): Promise<BackendTask> {
    if (isSimulatorActive()) return simUpdateTask(taskId, input);
    const result = await httpClient.patch<TaskResponse, UpdateTaskInput>(
      `/tasks/${encodeURIComponent(taskId)}`,
      input,
    );
    return result.task;
  },
};

export const notificationsApi = {
  async list(box: 'mine' | 'inbox' | 'sent' = 'mine'): Promise<NotificationListResponse> {
    if (isSimulatorActive()) {
      // A drill has a single shared training inbox; box is irrelevant.
      void box;
      const { notifications, unread } = simListNotifications();
      return { success: true, count: notifications.length, unread, notifications };
    }
    return httpClient.get<NotificationListResponse>(`/notifications?box=${box}`);
  },
  async create(input: CreateNotificationInput): Promise<OperationalNotification> {
    if (isSimulatorActive()) return simCreateNotification(input);
    const result = await httpClient.post<NotificationResponse, CreateNotificationInput>(
      '/notifications',
      input,
    );
    return result.notification;
  },
  async markRead(notificationId: string): Promise<OperationalNotification> {
    if (isSimulatorActive()) return simMarkNotificationRead(notificationId);
    const result = await httpClient.patch<NotificationResponse>(
      `/notifications/${encodeURIComponent(notificationId)}/read`,
    );
    return result.notification;
  },
};
