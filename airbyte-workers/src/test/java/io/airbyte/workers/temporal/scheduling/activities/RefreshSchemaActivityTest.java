/*
 * Copyright (c) 2022 Airbyte, Inc., all rights reserved.
 */

package io.airbyte.workers.temporal.scheduling.activities;

import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import io.airbyte.config.ActorCatalogFetchEvent;
import io.airbyte.config.persistence.ConfigRepository;
import io.airbyte.workers.temporal.sync.RefreshSchemaActivityImpl;
import java.io.IOException;
import java.time.OffsetDateTime;
import java.util.Optional;
import java.util.UUID;
import org.assertj.core.api.Assertions;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class RefreshSchemaActivityTest {

  static private ConfigRepository mConfigRepository;
  static private RefreshSchemaActivityImpl refreshSchemaActivity;

  static private final UUID SOURCE_ID = UUID.randomUUID();

  @BeforeEach
  void setUp() {
    mConfigRepository = mock(ConfigRepository.class);
    refreshSchemaActivity = new RefreshSchemaActivityImpl(Optional.of(mConfigRepository));
  }

  @Test
  void testShouldRefreshSchemaNoRecentRefresh() throws IOException {
    when(mConfigRepository.getMostRecentActorCatalogFetchEventForSource(SOURCE_ID)).thenReturn(Optional.empty());
    Assertions.assertThat(true).isEqualTo(refreshSchemaActivity.shouldRefreshSchema(SOURCE_ID));
  }

  @Test
  void testShouldRefreshSchemaRecentRefreshOver24HoursAgo() throws IOException {
    Long twoDaysAgo = OffsetDateTime.now().minusHours(48l).toEpochSecond();
    ActorCatalogFetchEvent fetchEvent = new ActorCatalogFetchEvent().withActorCatalogId(UUID.randomUUID()).withCreatedAt(twoDaysAgo);
    when(mConfigRepository.getMostRecentActorCatalogFetchEventForSource(SOURCE_ID)).thenReturn(Optional.ofNullable(fetchEvent));
    Assertions.assertThat(true).isEqualTo(refreshSchemaActivity.shouldRefreshSchema(SOURCE_ID));
  }

  @Test
  void testShouldRefreshSchemaRecentRefreshLessThan24HoursAgo() throws IOException {
    Long twelveHoursAgo = OffsetDateTime.now().minusHours(12l).toEpochSecond();
    ActorCatalogFetchEvent fetchEvent = new ActorCatalogFetchEvent().withActorCatalogId(UUID.randomUUID()).withCreatedAt(twelveHoursAgo);
    when(mConfigRepository.getMostRecentActorCatalogFetchEventForSource(SOURCE_ID)).thenReturn(Optional.ofNullable(fetchEvent));
    Assertions.assertThat(false).isEqualTo(refreshSchemaActivity.shouldRefreshSchema(SOURCE_ID));
  }

}
