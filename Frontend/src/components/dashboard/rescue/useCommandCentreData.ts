import { useCallback, useEffect, useState } from 'react';
import { getUsers, verifyToken } from '@/services/authApi';
import {
  notificationsApi,
  tasksApi,
  type BackendTask,
  type OperationalNotification,
} from '@/services/operationalApi';
import type { AuthUser, OfficerUser } from '@/types';

export interface SessionEvent {
  id: string;
  at: string;
  title: string;
  detail: string;
  tone: 'green' | 'amber' | 'red' | 'slate';
}

export function isOperationsPlanner(user: AuthUser | null): boolean {
  if (!user) return false;
  if (user.roleLevel === 2) return true;
  if (String(user.roleId ?? '').trim().toLowerCase() === 'role_2') return true;
  return String(user.roleName ?? '').toLowerCase().includes('operations planner');
}

const errorMessage = (error: unknown) =>
  error instanceof Error ? error.message : 'The request failed unexpectedly.';

export function useCommandCentreData(regionKey: string) {
  const [tasks, setTasks] = useState<BackendTask[]>([]);
  const [tasksLoading, setTasksLoading] = useState(true);
  const [tasksError, setTasksError] = useState<string | null>(null);

  const [officers, setOfficers] = useState<OfficerUser[]>([]);
  const [officersError, setOfficersError] = useState<string | null>(null);

  const [notifications, setNotifications] = useState<OperationalNotification[]>([]);
  const [notificationsError, setNotificationsError] = useState<string | null>(null);

  const [currentUser, setCurrentUser] = useState<AuthUser | null>(null);
  const [sessionEvents, setSessionEvents] = useState<SessionEvent[]>([]);
  const [refreshCounter, setRefreshCounter] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setTasksLoading(true);
    setTasksError(null);
    setOfficersError(null);
    setNotificationsError(null);

    tasksApi
      .list()
      .then((result) => {
        if (cancelled) return;
        // Backend tasks optionally carry a regionKey; keep region matches plus
        // unscoped records so no confirmed dispatch is hidden from command.
        const scoped = result.filter(
          (task) => !task.regionKey || task.regionKey === regionKey,
        );
        setTasks(scoped);
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setTasks([]);
          setTasksError(errorMessage(error));
        }
      })
      .finally(() => {
        if (!cancelled) setTasksLoading(false);
      });

    getUsers()
      .then((result) => {
        if (!cancelled) setOfficers(result);
      })
      .catch((error: unknown) => {
        if (!cancelled) setOfficersError(errorMessage(error));
      });

    notificationsApi
      .list('mine')
      .then((result) => {
        if (!cancelled) setNotifications(result.notifications ?? []);
      })
      .catch((error: unknown) => {
        if (!cancelled) setNotificationsError(errorMessage(error));
      });

    verifyToken()
      .then((user) => {
        if (!cancelled) setCurrentUser(user);
      })
      .catch(() => {
        if (!cancelled) setCurrentUser(null);
      });

    return () => {
      cancelled = true;
    };
  }, [regionKey, refreshCounter]);

  const refresh = useCallback(() => setRefreshCounter((value) => value + 1), []);

  const logSessionEvent = useCallback((event: Omit<SessionEvent, 'id' | 'at'>) => {
    setSessionEvents((current) => [
      {
        ...event,
        id: `session-${Date.now()}-${current.length}`,
        at: new Date().toISOString(),
      },
      ...current,
    ]);
  }, []);

  const upsertTask = useCallback((task: BackendTask) => {
    setTasks((current) => {
      const exists = current.some((item) => item.id === task.id);
      if (!task.regionKey || task.regionKey === regionKey) {
        return exists
          ? current.map((item) => (item.id === task.id ? task : item))
          : [task, ...current];
      }
      return current.filter((item) => item.id !== task.id);
    });
  }, [regionKey]);

  return {
    tasks,
    tasksLoading,
    tasksError,
    officers,
    officersError,
    notifications,
    notificationsError,
    currentUser,
    planner: isOperationsPlanner(currentUser),
    sessionEvents,
    logSessionEvent,
    upsertTask,
    refresh,
  };
}
