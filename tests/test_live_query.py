import asyncio
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, Mock, create_autospec, patch

from astrbot.api.message_components import Image, Plain

from .. import bili_client, main
from ..core.constant import LOGO_PATH
from ..core.data_manager import DataManager
from ..core.models import RenderPayload, SubscriptionRecord
from ..services.listener import DynamicListener
from ..services.renderer import Renderer


class LiveQueryTests(IsolatedAsyncioTestCase):
    def setUp(self):
        self.plugin = main.Main.__new__(main.Main)
        self.plugin.rai = False
        self.query = AsyncMock()
        self.plugin.bili_client = SimpleNamespace(get_live_info_by_uids=self.query)
        self.plugin.data_manager = DataManager.__new__(DataManager)
        self.subscriptions = {"qq:GroupMessage:100": [SubscriptionRecord(1)]}
        self.plugin.data_manager.data = {"bili_sub_list": self.subscriptions}
        self.event = Mock(
            unified_msg_origin="qq:GroupMessage:801_100",
            get_platform_name=Mock(return_value="aiocqhttp"),
            get_platform_id=Mock(return_value="qq"),
            get_group_id=Mock(return_value="100"),
        )

    async def test_members_see_only_their_groups_subscriptions(self):
        for session, uid in [
            ("qq:GroupMessage:801_100", 1),
            ("qq:GroupMessage:802_100", 2),
            ("qq:GroupMessage:802_1100", 3),
            ("qq:FriendMessage:100", 4),
            ("qq2:GroupMessage:100", 5),
        ]:
            self.subscriptions[session] = [SubscriptionRecord(uid)]
        self.query.return_value = {
            "1": {"live_status": 2},
            "2": {"live_status": 1, "room_id": 42},
        }
        for session in ("100", "801_100", "999_100"):
            self.event.unified_msg_origin = f"qq:GroupMessage:{session}"
            result = await self.plugin.list_live_subscriptions(self.event)
            self.query.assert_awaited_with([1, 2])
            self.assertIn("https://live.bilibili.com/42", result.chain[0].text)
            self.assertNotIn("UID 1", result.chain[0].text)

    async def test_telegram_topics_remain_separate(self):
        self.event.get_platform_name.return_value = "telegram"
        self.event.unified_msg_origin = "tg:GroupMessage:-100#7"
        self.event.get_group_id.return_value = "-100#7"
        for topic, uid in [("-100", 1), ("-100#7", 2), ("-100#8", 3)]:
            self.subscriptions[f"tg:GroupMessage:{topic}"] = [SubscriptionRecord(uid)]
        self.query.return_value = {}
        result = await self.plugin.list_live_subscriptions(self.event)
        self.query.assert_awaited_once_with([2])
        self.assertIn("没有人在直播", result.chain[0].text)

    async def test_batch_failure_keeps_live_rooms_before_and_after_it(self):
        self.subscriptions["qq:GroupMessage:100"] = [
            SubscriptionRecord(i) for i in range(1, 102)
        ]
        self.query.side_effect = [
            {"2": {"live_status": 1, "room_id": 42}},
            OSError("batch failed"),
            {"101": {"live_status": 1, "room_id": 99}},
        ]
        result = await self.plugin.list_live_subscriptions(self.event)
        self.assertEqual(
            [len(c.args[0]) for c in self.query.await_args_list], [50, 50, 1]
        )
        text = "".join(part.text for part in result.chain)
        self.assertLess(
            text.index("live.bilibili.com/42"), text.index("live.bilibili.com/99")
        )
        self.assertIn("50 位", text)

    async def test_distinguishes_partial_and_total_outage_from_no_live_rooms(self):
        self.subscriptions["qq:GroupMessage:100"] = [
            SubscriptionRecord(i) for i in range(1, 52)
        ]
        for responses, expected in [
            ([{}, OSError()], "另有 1 位暂时查不到"),
            ([OSError(), OSError()], "请稍后再试"),
            ([{}, {}], "没有人在直播"),
        ]:
            with self.subTest(expected=expected):
                self.query.side_effect = responses
                result = await self.plugin.list_live_subscriptions(self.event)
                self.assertIn(expected, result.chain[0].text)

    async def test_card_failure_keeps_earlier_cover_and_all_links(self):
        self.subscriptions["qq:GroupMessage:100"] = [
            SubscriptionRecord(i) for i in range(1, 5)
        ]
        self.query.return_value = {
            str(i): {
                "live_status": 1,
                "room_id": i,
                "cover_from_user": "cover" if i > 1 else "",
            }
            for i in range(1, 5)
        }
        self.plugin.rai = True
        self.plugin.dynamic_listener = DynamicListener.__new__(DynamicListener)
        self.plugin.dynamic_listener.logo_path_provider = lambda: LOGO_PATH
        render = AsyncMock(side_effect=[LOGO_PATH, None])
        self.plugin.renderer = SimpleNamespace(render_dynamic=render)
        result = await self.plugin.list_live_subscriptions(self.event)
        self.assertEqual(render.await_count, 2)
        for attempt in render.await_args_list:
            self.assertEqual(
                attempt.kwargs, {"umo": "qq:GroupMessage:100", "attempts": 1}
            )
        self.assertEqual([type(part) for part in result.chain], [Plain, Image, Plain])
        self.assertIn("live.bilibili.com/1", result.chain[0].text)
        for i in [2, 3, 4]:
            self.assertIn(f"live.bilibili.com/{i}", result.chain[2].text)

    async def test_slow_renderer_falls_back_to_text_for_every_room(self):
        async def stall(*args, **kwargs):
            await asyncio.Event().wait()

        self.plugin.rai = True
        self.plugin.dynamic_listener = Mock()
        self.plugin.renderer = SimpleNamespace(
            render_dynamic=AsyncMock(side_effect=stall)
        )
        rooms = [
            (i, {"room_id": i, "cover_from_user": "cover", "title": f"show {i}"})
            for i in (1, 2)
        ]
        with patch.object(main, "LIVE_QUERY_RENDER_SECONDS", 0.05):
            reply = await asyncio.wait_for(
                self.plugin._live_rooms_result(
                    rooms, "aiocqhttp", "qq:GroupMessage:100"
                ),
                2,
            )
        self.plugin.renderer.render_dynamic.assert_awaited_once()
        self.assertFalse(reply.use_t2i_)
        for i in (1, 2):
            self.assertIn(
                f"show {i}\nhttps://live.bilibili.com/{i}", reply.chain[0].text
            )

    async def test_all_covers_share_one_deadline(self):
        clock = Mock()
        clock.monotonic.return_value = 0

        async def render(*args, **kwargs):
            clock.monotonic.return_value = main.LIVE_QUERY_RENDER_SECONDS
            return LOGO_PATH

        self.plugin.rai = True
        self.plugin.dynamic_listener = Mock()
        self.plugin.renderer = SimpleNamespace(
            render_dynamic=AsyncMock(side_effect=render)
        )
        rooms = [(i, {"room_id": i, "cover_from_user": "cover"}) for i in (1, 2)]
        with patch.object(main, "time", clock):
            result = await self.plugin._live_rooms_result(
                rooms, "aiocqhttp", "qq:GroupMessage:100"
            )
        self.plugin.renderer.render_dynamic.assert_awaited_once()
        self.assertEqual([type(part) for part in result.chain], [Plain, Image, Plain])
        self.assertIn("UID 2", result.chain[-1].text)
        self.assertIn("live.bilibili.com/2", result.chain[-1].text)

    async def test_bilibili_empty_room_list_and_invalid_response(self):
        client = bili_client.BiliClient.__new__(bili_client.BiliClient)
        with (
            patch.object(client, "_apply_proxy"),
            patch.object(bili_client, "Api") as api,
        ):
            request = api.return_value.update_params
            for response in ([], {}, {"1": {"live_status": 1}}, None, {"1": "error"}):
                with self.subTest(response=response):
                    response_body = asyncio.get_running_loop().create_future()
                    response_body.set_result(response)
                    request.return_value.result = response_body
                    if response is None or response == {"1": "error"}:
                        with self.assertRaises(ValueError):
                            await client.get_live_info_by_uids([1])
                    else:
                        self.assertEqual(
                            await client.get_live_info_by_uids([1]), response or {}
                        )
                    request.assert_called_with(**{"uids[]": [1]})

    async def test_render_endpoint_argument_on_old_and_new_astrbot(self):
        async def legacy(tmpl, data, return_url, options):
            pass

        async def current(tmpl, data, return_url, options, umo=None):
            pass

        for api in [legacy, current]:
            with self.subTest(api=api.__name__):
                render = create_autospec(api, return_value=None)
                renderer = Renderer(SimpleNamespace(html_render=render), True)
                await renderer.render_dynamic(RenderPayload(), umo="group", attempts=1)
                render.assert_awaited_once()
                args = render.await_args.kwargs
                if api is current:
                    self.assertEqual(args["umo"], "group")
                else:
                    self.assertNotIn("umo", args)
