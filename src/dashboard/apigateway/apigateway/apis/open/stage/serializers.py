# -*- coding: utf-8 -*-
#
# TencentBlueKing is pleased to support the open source community by making
# 蓝鲸智云 - API 网关(BlueKing - APIGateway) available.
# Copyright (C) 2017 THL A29 Limited, a Tencent company. All rights reserved.
# Licensed under the MIT License (the "License"); you may not use this file except
# in compliance with the License. You may obtain a copy of the License at
#
#     http://opensource.org/licenses/MIT
#
# Unless required by applicable law or agreed to in writing, software distributed under
# the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND,
# either express or implied. See the License for the specific language governing permissions and
# limitations under the License.
#
# We undertake not to change the open source license (MIT license) applicable
# to the current version of the project delivered to anyone in the future.
#
import uuid
from typing import Optional

from django.conf import settings
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from rest_framework import serializers
from rest_framework.validators import UniqueTogetherValidator

from apigateway.apis.web.stage.validators import StageVarsValidator
from apigateway.apps.plugin.constants import PluginBindingScopeEnum
from apigateway.biz.constants import MAX_BACKEND_TIMEOUT_IN_SECOND
from apigateway.biz.validators import MaxCountPerGatewayValidator
from apigateway.common.django.validators import NameValidator
from apigateway.common.fields import CurrentGatewayDefault
from apigateway.common.i18n.field import SerializerTranslatedField
from apigateway.common.mixins.serializers import ExtensibleFieldMixin
from apigateway.common.plugin.header_rewrite import HeaderRewriteConvertor
from apigateway.core.constants import (
    DEFAULT_BACKEND_NAME,
    DEFAULT_LB_HOST_WEIGHT,
    STAGE_NAME_PATTERN,
    LoadBalanceTypeEnum,
)
from apigateway.core.models import Backend, BackendConfig, MicroGateway, Stage

from .constants import DOMAIN_PATTERN, HEADER_KEY_PATTERN


class StageV1SLZ(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    description = SerializerTranslatedField(default_field="description_i18n", allow_blank=True)
    description_en = serializers.CharField(required=False, write_only=True)


class ResourceVersionInStageSLZ(serializers.Serializer):
    version = serializers.CharField()


class StageWithResourceVersionV1SLZ(serializers.Serializer):
    name = serializers.CharField()
    resource_version = ResourceVersionInStageSLZ(allow_null=True)
    released = serializers.SerializerMethodField()

    def to_representation(self, instance):
        instance.resource_version = self.context["stage_release"].get(instance.id, {}).get("resource_version")
        return super().to_representation(instance)

    def get_released(self, obj):
        return bool(obj.resource_version)


class HostSLZ(serializers.Serializer):
    host = serializers.RegexField(DOMAIN_PATTERN)
    weight = serializers.IntegerField(min_value=1, required=False)

    class Meta:
        ref_name = "apis.open.stage.HostSLZ"


class UpstreamsSLZ(serializers.Serializer):
    loadbalance = serializers.ChoiceField(choices=LoadBalanceTypeEnum.get_choices())
    hosts = serializers.ListField(child=HostSLZ(), allow_empty=False)

    def __init__(self, *args, **kwargs):
        self.allow_empty = kwargs.pop("allow_empty", False)
        super().__init__(*args, **kwargs)

    def _update_hosts(self, data):
        """
        如果负载均衡类型为 RoundRobin 时，将权重设置为默认值
        """
        if data.get("loadbalance") != LoadBalanceTypeEnum.RR.value:
            return data

        for host in data["hosts"]:
            host["weight"] = DEFAULT_LB_HOST_WEIGHT
        return data

    def to_internal_value(self, data):
        if self.allow_empty and not data:
            return {}
        data = super().to_internal_value(data)
        return self._update_hosts(data)

    def to_representation(self, instance):
        if self.allow_empty and not instance:
            return {}
        return super().to_representation(instance)

    def validate(self, data):
        if data.get("loadbalance") == LoadBalanceTypeEnum.WRR.value:
            host_without_weight = [host for host in data["hosts"] if host.get("weight") is None]
            if host_without_weight:
                raise serializers.ValidationError(_("负载均衡类型为 Weighted-RR 时，Host 权重必填。"))
        return data


class TransformHeadersSLZ(serializers.Serializer):
    set = serializers.DictField(label="设置", child=serializers.CharField(), required=False, allow_empty=True)
    delete = serializers.ListField(label="删除", child=serializers.CharField(), required=False, allow_empty=True)

    def _validate_headers_key(self, value):
        for key in value:
            if not HEADER_KEY_PATTERN.match(key):
                raise serializers.ValidationError(_("Header 键由字母、数字、连接符（-）组成，长度小于100个字符。"))
        return value

    def validate_set(self, value):
        return self._validate_headers_key(value)

    def validate_delete(self, value):
        return self._validate_headers_key(value)


class StageProxyHTTPConfigSLZ(serializers.Serializer):
    timeout = serializers.IntegerField(max_value=MAX_BACKEND_TIMEOUT_IN_SECOND, min_value=1)
    upstreams = UpstreamsSLZ(allow_empty=False)
    transform_headers = TransformHeadersSLZ(required=False, default=dict)


class StageSLZ(ExtensibleFieldMixin, serializers.ModelSerializer):
    gateway = serializers.HiddenField(default=CurrentGatewayDefault())
    name = serializers.RegexField(
        STAGE_NAME_PATTERN,
        validators=[NameValidator()],
    )
    vars = serializers.DictField(
        label="环境变量",
        child=serializers.CharField(allow_blank=True, required=True),
        default=dict,
    )
    proxy_http = StageProxyHTTPConfigSLZ()
    micro_gateway_id = serializers.UUIDField(allow_null=True, required=False)
    description = SerializerTranslatedField(
        default_field="description_i18n", allow_blank=True, allow_null=True, max_length=512, required=False
    )

    class Meta:
        ref_name = "apps.stage.StageSLZ"
        model = Stage
        fields = (
            "gateway",
            "id",
            "name",
            "description",
            "description_en",
            "vars",
            "status",
            "proxy_http",
            "micro_gateway_id",
        )
        extra_kwargs = {
            "description_en": {
                "required": False,
            }
        }
        read_only_fields = ("id", "status")
        non_model_fields = ["proxy_http", "rate_limit"]
        lookup_field = "id"

        validators = [
            UniqueTogetherValidator(
                queryset=Stage.objects.all(),
                fields=["gateway", "name"],
                message=gettext_lazy("网关下环境名称已经存在。"),
            ),
            MaxCountPerGatewayValidator(
                Stage,
                max_count_callback=lambda gateway: settings.MAX_STAGE_COUNT_PER_GATEWAY,
                message=gettext_lazy("每个网关最多创建 {max_count} 个环境。"),
            ),
            StageVarsValidator(),
        ]

    def validate(self, data):
        self._validate_micro_gateway_stage_unique(data.get("micro_gateway_id"))
        return data

    def create(self, validated_data):
        # 1. save stage
        instance = super().create(validated_data)

        proxy_http_config = validated_data["proxy_http"]

        # 2. create default backend
        backend, _ = Backend.objects.get_or_create(
            gateway=instance.gateway,
            name=DEFAULT_BACKEND_NAME,
        )

        config = self._get_stage_backend_config(proxy_http_config)
        backend_config = BackendConfig(
            gateway=instance.gateway,
            backend=backend,
            stage=instance,
            config=config,
        )
        backend_config.save()

        # 3. create other backend config with empty host
        backends = Backend.objects.filter(gateway=instance.gateway).exclude(name=DEFAULT_BACKEND_NAME)
        backend_configs = []
        config = {
            "type": "node",
            "timeout": 30,
            "loadbalance": "roundrobin",
            "hosts": [{"scheme": "http", "host": "", "weight": 100}],
        }

        for backend in backends:
            backend_config = BackendConfig(
                gateway=instance.gateway,
                backend=backend,
                stage=instance,
                config=config,
            )
            backend_configs.append(backend_config)

        if backend_configs:
            BackendConfig.objects.bulk_create(backend_configs)

        # 4. create or update header rewrite plugin config
        stage_transform_headers = proxy_http_config.get("transform_headers") or {}
        stage_config = HeaderRewriteConvertor.transform_headers_to_plugin_config(stage_transform_headers)
        HeaderRewriteConvertor.sync_plugins(
            instance.gateway_id,
            PluginBindingScopeEnum.STAGE.value,
            {instance.id: stage_config},
            self.context["request"].user.username,
        )

        return instance

    def _get_stage_backend_config(self, proxy_http_config):
        hosts = []
        for host in proxy_http_config["upstreams"]["hosts"]:
            scheme, _host = host["host"].rstrip("/").split("://")
            hosts.append({"scheme": scheme, "host": _host, "weight": host["weight"]})

        return {
            "type": "node",
            "timeout": proxy_http_config["timeout"],
            "loadbalance": proxy_http_config["upstreams"]["loadbalance"],
            "hosts": hosts,
        }

    def update(self, instance, validated_data):
        validated_data.pop("name", None)
        # 仅能通过发布更新 status，不允许直接更新 status
        validated_data.pop("status", None)
        validated_data.pop("created_by", None)

        # 1. 更新数据
        instance = super().update(instance, validated_data)

        proxy_http_config = validated_data["proxy_http"]

        # 2. create default backend
        backend, _ = Backend.objects.get_or_create(
            gateway=instance.gateway,
            name=DEFAULT_BACKEND_NAME,
        )

        backend_config = BackendConfig.objects.filter(
            gateway=instance.gateway,
            backend=backend,
            stage=instance,
        ).first()
        if not backend_config:
            backend_config = BackendConfig(
                gateway=instance.gateway,
                backend=backend,
                stage=instance,
            )

        backend_config.config = self._get_stage_backend_config(proxy_http_config)
        backend_config.save()

        # 3. create or update header rewrite plugin config
        stage_transform_headers = proxy_http_config.get("transform_headers") or {}
        stage_config = HeaderRewriteConvertor.transform_headers_to_plugin_config(stage_transform_headers)
        HeaderRewriteConvertor.sync_plugins(
            instance.gateway_id,
            PluginBindingScopeEnum.STAGE.value,
            {instance.id: stage_config},
            self.context["request"].user.username,
        )

        return instance

    def validate_micro_gateway_id(self, value) -> Optional[uuid.UUID]:
        if value is None:
            return None

        gateway = self.context["request"].gateway
        if not MicroGateway.objects.filter(gateway=gateway, id=value).exists():
            raise serializers.ValidationError(_("微网关实例不存在，id={value}。").format(value=value))

        return value

    def _validate_micro_gateway_stage_unique(self, micro_gateway_id: Optional[uuid.UUID]):
        """校验 micro_gateway 仅绑定到一个环境"""
        if not micro_gateway_id:
            return

        queryset = Stage.objects.filter(micro_gateway_id=micro_gateway_id)
        if self.instance is not None:
            queryset = queryset.exclude(pk=self.instance.pk)

        if queryset.exists():
            raise serializers.ValidationError(_("微网关实例已绑定到其它环境。"))
