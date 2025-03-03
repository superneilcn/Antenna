from modules.api.models import ApiKey
from modules.template.models import Template

from django_filters.rest_framework import DjangoFilterBackend
from modules.task.constants import TASK_STATUS, TASK_TMP
from modules.task.models import Task, TaskConfig, TaskConfigItem
from modules.task.serializers import TaskConfigItemSerializer, TaskInfoSerializer, CreateTaskSerializer, \
    DeleteTmpTaskSerializer, CreateTaskConfigItemSerializer
from rest_framework import mixins, status
from rest_framework.decorators import action
from rest_framework.filters import SearchFilter
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet
from utils.helper import generate_code, get_payload


class TaskInfoViewSet(GenericViewSet, mixins.ListModelMixin, mixins.CreateModelMixin, mixins.UpdateModelMixin,
                      mixins.DestroyModelMixin, ):
    queryset = Task.objects.all().order_by("id")
    serializer_class = TaskInfoSerializer
    filter_backends = (DjangoFilterBackend, SearchFilter)
    filter_fields = ("status",)
    search_fields = ('name',)
    permission_classes = (IsAuthenticated,)

    def get_queryset(self):
        return Task.objects.filter(user=self.request.user, is_tmp=TASK_TMP.FORMAL)

    @action(methods=["GET"], detail=False, permission_classes=[IsAuthenticated, ])
    def create_tmp_task(self, request, *args, **kwargs):
        """
        创建缓存任务，创建缓存任务默认添加dns与http组件
        """

        task = Task.objects.create(name='', user=self.request.user, status=TASK_STATUS.OPEN, is_tmp=TASK_TMP.TMP)
        return Response(
            {"task_info": {"task_id": task.id, "task_name": "", "callback_url": "", "callback_url_headers": "",
                           "show_dashboard": False},
             "listen_template_info": [],
             "payload_template_info": [], }, status=status.HTTP_200_OK)

    @action(methods=["POST"], detail=False, permission_classes=[IsAuthenticated, ])
    def cancel_tmp_task(self, request, *args, **kwargs):
        """
        取消缓存任务，
        {"task_id":}
        """
        data = request.data
        serializer = DeleteTmpTaskSerializer(data=data, context={'user': self.request.user})
        serializer.is_valid(raise_exception=True)
        try:
            task_id = request.data["task_id"]
            Task.objects.filter(user=self.request.user, id=task_id).delete()
            return Response({"task_id": task_id}, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({"code": 0, "message": f"错误原因:{e}"}, status=status.HTTP_200_OK)

    @action(methods=["POST"], detail=False, permission_classes=[IsAuthenticated, ])
    def create_task(self, request, *args, **kwargs):
        """
        将缓存任务变成正式任务

        {"task_id":20,
        "task_name":"1111",
        "callback_url":"",
        "callback_url_headers":"",
        "show_dashboard":true}
        """
        task_info = request.data
        serializer = CreateTaskSerializer(data=task_info)
        serializer.is_valid(raise_exception=True)
        task_id = int(task_info.get("task_id", "0"))
        task_name = task_info.get("task_name", "")
        callback_url = task_info.get("callback_url", "")
        callback_url_headers = task_info.get("callback_url_headers", "")
        show_dashboard = int(task_info.get("show_dashboard", 0))

        try:
            Task.objects.filter(id=task_id).update(name=task_name, callback_url=callback_url,
                                                   callback_url_headers=callback_url_headers,
                                                   show_dashboard=show_dashboard, is_tmp=TASK_TMP.FORMAL)
            return Response(data=request.data, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({"code": 0, "message": f"错误原因:{e}"}, status=status.HTTP_200_OK)

    @action(methods=["POST"], detail=False, permission_classes=[IsAuthenticated, ])
    def multi_update_status(self, request, *args, **kwargs):
        """
        批量修改任务状态
        {
        "id":[1,2,3,4,5,]
        "status":1
        }
        """
        task_list = request.data.get("id", "")
        task_status = bool(request.data.get("status", ""))

        if not task_list or task_status not in list(TASK_STATUS):
            return Response({"code": 0, "message": "传递参数值格式错误"}, status=status.HTTP_200_OK)
        Task.objects.filter(user_id=self.request.user.id, id__in=task_list).update(status=task_status)
        return Response(data=request.data, status=status.HTTP_200_OK)

    @action(methods=['delete'], detail=False, permission_classes=[IsAuthenticated])
    def multiple_delete(self, request, *args, **kwargs):
        """
        批量删除任务
        """
        delete_id = request.query_params.get('id', None)
        if not delete_id:
            return Response({"message": "删除失败,输入参数格式错误", "code": 0}, status=status.HTTP_200_OK)
        Task.objects.filter(id__in=delete_id.split(',')).delete()
        return Response({"message": "success", "code": 1}, status=status.HTTP_200_OK)


class TaskConfigItemViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, GenericViewSet):
    queryset = TaskConfigItem.objects.all().order_by("id")
    serializer_class = TaskConfigItemSerializer
    filter_backends = (DjangoFilterBackend, SearchFilter)
    filter_fields = ("task", "task_config_id")
    permission_classes = (IsAuthenticated,)

    def get_queryset(self):
        user_id = self.request.user.id
        return TaskConfigItem.objects.filter(task_config__task__user=user_id)

    @staticmethod
    def get_result_data(data):
        """
        修改任务详情接口返回格式
        """
        if not data:
            return Response(data={}, status=status.HTTP_200_OK)
        listen_data_list = []
        payload_data_list = []
        for i in data:
            task_config_status = 1
            task_config_id = i["task_config"]
            template_id = i["template"]
            task_id = i["task"]
            task_config_item_id = i["id"]
            template_config_item_id = i["template_config_item"]
            value = i["value"]
            key = TaskConfig.objects.get(id=task_config_id).key
            template_record = Template.objects.get(id=template_id)
            url = get_payload(key, template_record.payload)
            for _data_old in payload_data_list:
                if task_config_id == _data_old.get("task_config_id", 0):
                    _data_old["task_config_item_list"].append({
                        "template_config_item": template_config_item_id,
                        "id": task_config_item_id,
                        "value": value})
                    task_config_status = 0
            if task_config_status:
                _data = {
                    "task": task_id,
                    "template": template_id,
                    "template_name": template_record.name,
                    "template_type": template_record.type,
                    "template_choice_type": template_record.choice_type,
                    "task_config_id": task_config_id,
                    "key": url,
                    "task_config_item_list": [{
                        "template_config_item": template_config_item_id,
                        "id": task_config_item_id,
                        "value": value}]
                }

                if template_record.type == 1:
                    listen_data_list.append(_data)
                else:
                    payload_data_list.append(_data)
        task_record = Task.objects.get(id=int(data[0]["task"]))
        result = {
            "task_info": {
                "task_id": task_id,
                "task_name": task_record.name,
                "callback_url": task_record.callback_url,
                "callback_url_headers": task_record.callback_url_headers,
                "show_dashboard": bool(task_record.show_dashboard)},
            "listen_template_info": listen_data_list,
            "payload_template_info": payload_data_list,
        }
        return Response(result, status=status.HTTP_200_OK)

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_result_data(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return self.get_result_data(serializer.data)

    def create(self, request, *args, **kwargs):
        """
        添加组件实例
        {
    "template": 32,
    "template_config_item_list": [
        {
            "template_config_item": 52,
            "id": 7,
            "value": {
                "ip": "219.137.78.61",
                "port": 75
            }
        },
    ],
    "task": 1,
}
        """
        serializer = CreateTaskConfigItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        task_id = serializer.data["task"]
        template_id = serializer.data["template"]
        code = generate_code(4)
        task_config = TaskConfig.objects.create(task_id=task_id, key=code)
        template_config_item_list = request.data["template_config_item_list"]
        for template_config_item in template_config_item_list:
            template_config_item_id = int(template_config_item.get("template_config_item", 0))
            values = template_config_item.get("value", {})
            TaskConfigItem.objects.create(value=values, template_config_item_id=template_config_item_id,
                                          task_id=task_id,
                                          template_id=template_id, task_config_id=task_config.id)
        queryset = self.filter_queryset(
            TaskConfigItem.objects.filter(task_config__task__user=self.request.user.id, task_id=task_id))
        serializer = self.get_serializer(queryset, many=True)
        return self.get_result_data(serializer.data)

    @action(methods=["POST"], detail=False, permission_classes=[IsAuthenticated])
    def update_config(self, request, *args, **kwargs):
        """
        修改组件实例
        {
    "task": 242,
    "template": 4,
    "task_config":5,
    "template_config_item_list": [
        {
            "id":1,
            "value": {
                "ip": "247.233.48.108",
                "port": 90
            },
            "template_config_item": 12
        }]
}
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        task_id = serializer.data["task"]
        template_id = serializer.data["template"]
        task_config_id = serializer.data["task_config"]
        TaskConfigItem.objects.filter(task_config_id=task_config_id).delete()
        TaskConfig.objects.filter(id=task_config_id).delete()
        template_config_item_list = request.data["template_config_item_list"]
        code = generate_code(4)
        new_task_config = TaskConfig.objects.create(task_id=task_id, key=code)
        new_task_config_id = int(new_task_config.id)
        for template_config_item in template_config_item_list:
            template_config_item_id = int(template_config_item.get("template_config_item", 0))
            values = template_config_item.get("value", {})
            TaskConfigItem.objects.create(value=values, template_config_item_id=template_config_item_id,
                                          task_id=task_id,
                                          template_id=template_id, task_config_id=new_task_config_id)
        queryset = self.filter_queryset(
            TaskConfigItem.objects.filter(task_config__task__user=self.request.user.id, task_id=task_id))
        serializer = self.get_serializer(queryset, many=True)
        return self.get_result_data(serializer.data)

    @action(methods=["delete"], detail=False, permission_classes=[IsAuthenticated])
    def delete_config(self, request, *args, **kwargs):
        """
        删除组件实例
        """
        task_config_id = int(request.query_params.get('id', None))
        task_config = TaskConfig.objects.filter(id=task_config_id, task__user_id=self.request.user.id).first()
        if not task_config:
            return Response({"code": 1, "message": "任务不存在"})
        task_id = task_config.task_id
        TaskConfig.objects.filter(id=task_config_id).delete()
        TaskConfigItem.objects.filter(task_config_id=task_config_id).delete()
        queryset = self.filter_queryset(
            TaskConfigItem.objects.filter(task_config__task__user=self.request.user.id, task_id=task_id))
        serializer = self.get_serializer(queryset, many=True)
        return self.get_result_data(serializer.data)

    @action(methods=["GET"], detail=False, permission_classes=[AllowAny, ])
    def api(self, request, *args, **kwargs):
        """
        提供api查询获取当前可用payload
        """
        apikey = self.request.query_params.get('apikey', '')
        key = ApiKey.objects.filter(key=apikey).first()
        if not key:
            return Response({"code": 0, "message": "apikey错误"}, status=status.HTTP_400_BAD_REQUEST)
        task_config_item_record = TaskConfigItem.objects.filter(task__user=key.user_id, task__status=1,
                                                                task__show_dashboard=1)
        payload_list = []
        if task_config_item_record:
            for task_config_item in task_config_item_record:
                payload = task_config_item.template.payload
                key = task_config_item.task_config.key
                payload = get_payload(key, payload)
                if payload not in payload_list:
                    payload_list.append(payload)
        return Response(data={"payload": payload_list}, status=status.HTTP_200_OK)
