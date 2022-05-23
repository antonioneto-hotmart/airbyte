#
# Copyright (c) 2021 Airbyte, Inc., all rights reserved.
#

from abc import abstractmethod
from typing import Tuple

from airbyte_cdk.sources.abstract_source import AbstractSource
from airbyte_cdk.sources.configurable.checks.connection_checker import ConnectionChecker


class ConfigurableSource(AbstractSource):
    """
    Base class for configurable Source. Concrete sources need to define the connection_checker to use
    """

    @property
    @abstractmethod
    def connection_checker(self) -> ConnectionChecker:
        pass

    def check_connection(self, logger, config) -> Tuple[bool, any]:
        return self.connection_checker.check_connection(self, logger, config)
