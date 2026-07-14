import { createBrowserRouter } from "react-router-dom";
import { TabLayout } from "@/components/layout/TabLayout";
import { StackLayout } from "@/components/layout/StackLayout";
import { RequireAuth } from "@/features/auth/RequireAuth";
import { LoginPage } from "@/features/auth/LoginPage";
import { SignUpPage } from "@/features/auth/SignUpPage";
import { ConfirmSignUpPage } from "@/features/auth/ConfirmSignUpPage";
import { HomePage } from "@/features/home/HomePage";
import { NotificationsStubPage } from "@/features/home/NotificationsStubPage";
import { MyPage } from "@/features/user/MyPage";
import { ProfileEditPage } from "@/features/user/ProfileEditPage";
import { CommunityListPage } from "@/features/community/CommunityListPage";
import { CommunityCreatePage } from "@/features/community/CommunityCreatePage";
import { CommunityDetailPage } from "@/features/community/CommunityDetailPage";
import { InvitePage } from "@/features/community/InvitePage";
import { InviteAcceptPage } from "@/features/community/InviteAcceptPage";
import { JoinRequestListPage } from "@/features/community/JoinRequestListPage";
import { MemberListPage } from "@/features/community/MemberListPage";
import { AvailabilityListPage } from "@/features/availability/AvailabilityListPage";
import { AvailabilityCalendarPage } from "@/features/availability/AvailabilityCalendarPage";
import { AvailabilityRequestListPage } from "@/features/availability/AvailabilityRequestListPage";
import { AvailabilityRequestCreatePage } from "@/features/availability/AvailabilityRequestCreatePage";
import { paths } from "@/routes/paths";

export const router = createBrowserRouter([
  { path: paths.login, element: <LoginPage /> },
  { path: paths.signup, element: <SignUpPage /> },
  { path: paths.signupConfirm, element: <ConfirmSignUpPage /> },
  {
    path: "/invite/:token",
    element: (
      <RequireAuth>
        <InviteAcceptPage />
      </RequireAuth>
    ),
  },
  {
    element: (
      <RequireAuth>
        <TabLayout />
      </RequireAuth>
    ),
    children: [
      { path: paths.home, element: <HomePage /> },
      { path: paths.communityList, element: <CommunityListPage /> },
      { path: paths.availabilityList, element: <AvailabilityListPage /> },
      { path: paths.notifications, element: <NotificationsStubPage /> },
      { path: paths.myPage, element: <MyPage /> },
    ],
  },
  {
    element: (
      <RequireAuth>
        <StackLayout />
      </RequireAuth>
    ),
    children: [
      {
        path: "/communities/new",
        element: <CommunityCreatePage />,
        handle: { title: "コミュニティ作成" },
      },
      {
        path: "/communities/:communityId",
        element: <CommunityDetailPage />,
        handle: { title: "コミュニティ詳細" },
      },
      {
        path: "/communities/:communityId/invite",
        element: <InvitePage />,
        handle: { title: "メンバーを招待" },
      },
      {
        path: "/communities/:communityId/join-requests",
        element: <JoinRequestListPage />,
        handle: { title: "参加リクエスト" },
      },
      {
        path: "/communities/:communityId/members",
        element: <MemberListPage />,
        handle: { title: "メンバー一覧" },
      },
      {
        path: "/communities/:communityId/availability/new",
        element: <AvailabilityCalendarPage />,
        handle: { title: "空き予定登録" },
      },
      {
        path: "/communities/:communityId/availability-requests",
        element: <AvailabilityRequestListPage />,
        handle: { title: "空き予定提出リクエスト" },
      },
      {
        path: "/communities/:communityId/availability-requests/new",
        element: <AvailabilityRequestCreatePage />,
        handle: { title: "提出リクエスト作成" },
      },
      {
        path: "/mypage/profile",
        element: <ProfileEditPage />,
        handle: { title: "プロフィール編集" },
      },
    ],
  },
]);
