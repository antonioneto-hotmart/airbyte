#
# Copyright (c) 2022 Airbyte, Inc., all rights reserved.
#

import json
from asyncio import gather, get_event_loop
from typing import Dict, Generator

from airbyte_cdk.logger import AirbyteLogger
from airbyte_cdk.models import (
    AirbyteCatalog,
    AirbyteConnectionStatus,
    AirbyteMessage,
    AirbyteStream,
    ConfiguredAirbyteCatalog,
    Status,
    SyncMode,
)
from airbyte_cdk.sources import Source
from firebolt.async_db import Connection as AsyncConnection

from .database import establish_async_connection, establish_connection, get_firebolt_tables
from .utils import airbyte_message_from_data, convert_type

SUPPORTED_SYNC_MODES = [SyncMode.full_refresh]


async def get_table_stream(connection: AsyncConnection, table: str) -> AirbyteStream:
    """
    Get AirbyteStream for a particular table with table structure defined.

    :param connection: Connection object connected to a database

    :return: AirbyteStream object containing the table structure
    """
    column_mapping = {}
    cursor = connection.cursor()
    await cursor.execute(f"SHOW COLUMNS {table}")
    for t_name, c_name, c_type, nullable in await cursor.fetchall():
        airbyte_type = convert_type(c_type, nullable)
        column_mapping[c_name] = airbyte_type
    cursor.close()
    json_schema = {
        "type": "object",
        "properties": column_mapping,
    }
    return AirbyteStream(name=table, json_schema=json_schema, supported_sync_modes=SUPPORTED_SYNC_MODES)


class SourceFirebolt(Source):
    def check(self, logger: AirbyteLogger, config: json) -> AirbyteConnectionStatus:
        """
        Tests if the input configuration can be used to successfully connect to the integration
            e.g: if a provided Stripe API token can be used to connect to the Stripe API.

        :param logger: Logging object to display debug/info/error to the logs
            (logs will not be accessible via airbyte UI if they are not passed to this logger)
        :param config: Json object containing the configuration of this source, content of this json is as specified in
        the properties of the spec.json file

        :return: AirbyteConnectionStatus indicating a Success or Failure
        """
        try:
            with establish_connection(config, logger) as connection:
                # We can only verify correctness of connection parameters on execution
                with connection.cursor() as cursor:
                    cursor.execute("SELECT 1")
                return AirbyteConnectionStatus(status=Status.SUCCEEDED)
        except Exception as e:
            return AirbyteConnectionStatus(status=Status.FAILED, message=f"An exception occurred: {str(e)}")

    def discover(self, logger: AirbyteLogger, config: json) -> AirbyteCatalog:
        """
        Returns an AirbyteCatalog representing the available streams and fields in this integration.
        For example, given valid credentials to a Postgres database,
        returns an Airbyte catalog where each postgres table is a stream, and each table column is a field.

        :param logger: Logging object to display debug/info/error to the logs
            (logs will not be accessible via airbyte UI if they are not passed to this logger)
        :param config: Json object containing the configuration of this source, content of this json is as specified in
        the properties of the spec.json file

        :return: AirbyteCatalog is an object describing a list of all available streams in this source.
            A stream is an AirbyteStream object that includes:
            - its stream name (or table name in the case of Postgres)
            - json_schema providing the specifications of expected schema for this stream (a list of columns described
            by their names and types)
        """

        async def get_streams():
            async with await establish_async_connection(config, logger) as connection:
                tables = await get_firebolt_tables(connection)
                logger.info(f"Found {len(tables)} available tables.")
                return await gather(*[get_table_stream(connection, table) for table in tables])

        loop = get_event_loop()
        streams = loop.run_until_complete(get_streams())
        logger.info(f"Provided {len(streams)} streams to the Aribyte Catalog.")
        return AirbyteCatalog(streams=streams)

    def read(
        self,
        logger: AirbyteLogger,
        config: json,
        catalog: ConfiguredAirbyteCatalog,
        state: Dict[str, any],
    ) -> Generator[AirbyteMessage, None, None]:
        """
        Returns a generator of the AirbyteMessages generated by reading the source with the given configuration,
        catalog, and state.

        :param logger: Logging object to display debug/info/error to the logs
            (logs will not be accessible via airbyte UI if they are not passed to this logger)
        :param config: Json object containing the configuration of this source, content of this json is as specified in
            the properties of the spec.json file
        :param catalog: The input catalog is a ConfiguredAirbyteCatalog which is almost the same as AirbyteCatalog
            returned by discover(), but
        in addition, it's been configured in the UI! For each particular stream and field, there may have been provided
        with extra modifications such as: filtering streams and/or columns out, renaming some entities, etc
        :param state: When a Airbyte reads data from a source, it might need to keep a checkpoint cursor to resume
            replication in the future from that saved checkpoint.
            This is the object that is provided with state from previous runs and avoid replicating the entire set of
            data everytime.

        :return: A generator that produces a stream of AirbyteRecordMessage contained in AirbyteMessage object.
        """

        logger.info(f"Reading data from {len(catalog.streams)} Firebolt tables.")
        with establish_connection(config, logger) as connection:
            with connection.cursor() as cursor:
                for c_stream in catalog.streams:
                    table_name = c_stream.stream.name
                    table_properties = c_stream.stream.json_schema["properties"]
                    columns = list(table_properties.keys())

                    # Escape columns with " to avoid reserved keywords e.g. id
                    escaped_columns = ['"{}"'.format(col) for col in columns]

                    query = "SELECT {columns} FROM {table}".format(columns=",".join(escaped_columns), table=table_name)
                    cursor.execute(query)

                    logger.info(f"Fetched {cursor.rowcount} rows from table {table_name}.")
                    for result in cursor.fetchall():
                        message = airbyte_message_from_data(result, columns, table_name)
                        if message:
                            yield message
        logger.info("Data read complete.")
