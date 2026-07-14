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

  availabilityList: "/availability",
  availabilityNew: (communityId: string) => `/communities/${communityId}/availability/new`,
  availabilityRequestList: (communityId: string) =>
    `/communities/${communityId}/availability-requests`,
  availabilityRequestNew: (communityId: string) =>
    `/communities/${communityId}/availability-requests/new`,

  notifications: "/notifications",

  myPage: "/mypage",
  profileEdit: "/mypage/profile",
} as const;
