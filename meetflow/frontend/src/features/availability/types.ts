import type { GameType } from "@/features/user/types";

/** backend/functions/availability_lambda/handlers/availability.py の _to_api_availability() */
export type Availability = {
  availabilityId: string;
  startTime: string;
  endTime: string;
  gameTypes: GameType[];
  comment: string;
};

export type AvailabilityInput = {
  startTime: string;
  endTime: string;
  gameTypes?: GameType[];
  comment?: string;
};

export type AvailabilityRequestScope = "ALL" | "SPECIFIED";

/** availability_requests.py の _to_api_request() */
export type AvailabilityRequest = {
  requestId: string;
  targetPeriodStart: string;
  targetPeriodEnd: string;
  deadline: string;
  targetScope: AvailabilityRequestScope;
  targetUserIds: string[];
  message: string;
  createdBy: string;
  createdAt: string;
};

export type CreateAvailabilityRequestInput = {
  targetPeriodStart: string;
  targetPeriodEnd: string;
  deadline: string;
  targetScope: AvailabilityRequestScope;
  targetUserIds?: string[];
  message?: string;
};

export type PendingMember = {
  userId: string;
  nickname: string;
};
