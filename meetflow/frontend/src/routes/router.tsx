import { createBrowserRouter } from "react-router-dom";
import { TabLayout } from "@/components/layout/TabLayout";
import { StackLayout } from "@/components/layout/StackLayout";
import { RequireAuth } from "@/features/auth/RequireAuth";
import { LoginPage } from "@/features/auth/LoginPage";
import { SignUpPage } from "@/features/auth/SignUpPage";
import { ConfirmSignUpPage } from "@/features/auth/ConfirmSignUpPage";
import { HomePage } from "@/features/home/HomePage";
import { MyPage } from "@/features/user/MyPage";
import { ProfileEditPage } from "@/features/user/ProfileEditPage";
import { CommunityListPage } from "@/features/community/CommunityListPage";
import { CommunityCreatePage } from "@/features/community/CommunityCreatePage";
import { CommunityDetailPage } from "@/features/community/CommunityDetailPage";
import { DisplayNameEditPage } from "@/features/community/DisplayNameEditPage";
import { InvitePage } from "@/features/community/InvitePage";
import { InviteAcceptPage } from "@/features/community/InviteAcceptPage";
import { JoinRequestListPage } from "@/features/community/JoinRequestListPage";
import { MemberListPage } from "@/features/community/MemberListPage";
import { AvailabilityListPage } from "@/features/availability/AvailabilityListPage";
import { AvailabilityCalendarPage } from "@/features/availability/AvailabilityCalendarPage";
import { AvailabilityRequestListPage } from "@/features/availability/AvailabilityRequestListPage";
import { AvailabilityRequestCreatePage } from "@/features/availability/AvailabilityRequestCreatePage";
import { EventTemplateListPage } from "@/features/matching/EventTemplateListPage";
import { EventTemplateFormPage } from "@/features/matching/EventTemplateFormPage";
import { MatchingCandidateListPage } from "@/features/matching/MatchingCandidateListPage";
import { MatchingCandidateDetailPage } from "@/features/matching/MatchingCandidateDetailPage";
import { EventListPage } from "@/features/event/EventListPage";
import { EventDetailPage } from "@/features/event/EventDetailPage";
import { CancelRequestCreatePage } from "@/features/event/CancelRequestCreatePage";
import { CancelRequestListPage } from "@/features/event/CancelRequestListPage";
import { ResultSessionCreatePage } from "@/features/result/ResultSessionCreatePage";
import { ResultSummaryPage } from "@/features/result/ResultSummaryPage";
import { NotificationListPage } from "@/features/notification/NotificationListPage";
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
      { path: paths.notifications, element: <NotificationListPage /> },
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
        path: "/communities/:communityId/display-name",
        element: <DisplayNameEditPage />,
        handle: { title: "表示名を変更" },
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
      {
        path: "/communities/:communityId/event-templates",
        element: <EventTemplateListPage />,
        handle: { title: "開催条件" },
      },
      {
        path: "/communities/:communityId/event-templates/new",
        element: <EventTemplateFormPage />,
        handle: { title: "開催条件を追加" },
      },
      {
        path: "/communities/:communityId/event-templates/:templateId/edit",
        element: <EventTemplateFormPage />,
        handle: { title: "開催条件を編集" },
      },
      {
        path: "/communities/:communityId/matching/candidates",
        element: <MatchingCandidateListPage />,
        handle: { title: "マッチング候補" },
      },
      {
        path: "/communities/:communityId/matching/candidates/:candidateId",
        element: <MatchingCandidateDetailPage />,
        handle: { title: "候補詳細" },
      },
      {
        path: "/communities/:communityId/events",
        element: <EventListPage />,
        handle: { title: "イベント一覧" },
      },
      {
        path: "/events/:eventId",
        element: <EventDetailPage />,
        handle: { title: "イベント詳細" },
      },
      {
        path: "/events/:eventId/cancel-request",
        element: <CancelRequestCreatePage />,
        handle: { title: "キャンセル申請" },
      },
      {
        path: "/events/:eventId/cancel-requests",
        element: <CancelRequestListPage />,
        handle: { title: "キャンセル申請一覧" },
      },
      {
        path: "/events/:eventId/sessions/new",
        element: <ResultSessionCreatePage />,
        handle: { title: "成績登録" },
      },
      {
        path: "/communities/:communityId/results/:userId",
        element: <ResultSummaryPage />,
        handle: { title: "成績" },
      },
    ],
  },
]);
