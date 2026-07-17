/** 画面遷移で使うパスを一元管理する（生のテンプレート文字列を画面側に書かない） */
export const paths = {
  login: "/login",
  signup: "/signup",
  signupConfirm: "/signup/confirm",
  inviteAccept: (token: string) => `/invite/${token}`,

  home: "/",
  communityList: "/communities",
  communityNew: "/communities/new",
  communityDetail: (communityId: string) => `/communities/${communityId}`,
  communityInvite: (communityId: string) => `/communities/${communityId}/invite`,
  communityJoinRequests: (communityId: string) => `/communities/${communityId}/join-requests`,
  communityMembers: (communityId: string) => `/communities/${communityId}/members`,
  communityDisplayNameEdit: (communityId: string) => `/communities/${communityId}/display-name`,
  communityThemeColorEdit: (communityId: string) => `/communities/${communityId}/theme-color`,
  communityAutoApproveEdit: (communityId: string) => `/communities/${communityId}/auto-approve`,
  communityFrequencyLimitEdit: (communityId: string) =>
    `/communities/${communityId}/frequency-limit`,

  availabilityList: "/availability",
  availabilityNew: (communityId: string) => `/communities/${communityId}/availability/new`,
  availabilityCalendar: (communityId: string) => `/communities/${communityId}/availability`,
  availabilityRequestList: (communityId: string) =>
    `/communities/${communityId}/availability-requests`,
  availabilityRequestNew: (communityId: string) =>
    `/communities/${communityId}/availability-requests/new`,

  eventTemplateList: (communityId: string) => `/communities/${communityId}/event-templates`,
  eventTemplateNew: (communityId: string) => `/communities/${communityId}/event-templates/new`,
  eventTemplateEdit: (communityId: string, templateId: string) =>
    `/communities/${communityId}/event-templates/${templateId}/edit`,
  matchingCandidateList: (communityId: string) =>
    `/communities/${communityId}/matching/candidates`,
  matchingCandidateDetail: (communityId: string, candidateId: string) =>
    `/communities/${communityId}/matching/candidates/${candidateId}`,

  eventList: (communityId: string) => `/communities/${communityId}/events`,
  eventDetail: (eventId: string) => `/events/${eventId}`,
  eventCancelRequest: (eventId: string) => `/events/${eventId}/cancel-request`,
  eventCancelRequestList: (eventId: string) => `/events/${eventId}/cancel-requests`,

  resultSessionNew: (eventId: string) => `/events/${eventId}/sessions/new`,
  resultSessionEdit: (eventId: string, sessionNo: string) =>
    `/events/${eventId}/sessions/${sessionNo}/edit`,
  resultSummary: (communityId: string, userId: string) =>
    `/communities/${communityId}/results/${userId}`,

  notifications: "/notifications",

  myPage: "/mypage",
  profileEdit: "/mypage/profile",

  feedbackNew: "/feedback",
  feedbackAdmin: "/feedback/admin",
  announcementList: "/announcements",
} as const;
