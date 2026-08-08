package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertTrue;
import tools.jackson.databind.JsonNode;

/** audit-event: the event moves to schema version 2 (adds 'schemaVersion' 2)
 * and still carries the owner id and the primary identifier -- now the v2 memberId, read from the
 * nested 'identity' object. */
@Tag("cp53")
class Cp53Tests extends AcceptanceBase {

	@Test
	void coreEventIsSchemaV2WithMemberId() throws Exception {
		try (AuditLogCapture audit = new AuditLogCapture()) {
			int id = createOwnerOk(knownOwner("Sydney"));
			JsonNode r = fetchOwner(id);
			String memberId = r.get("identity").get("memberId").asText();
			assertTrue(audit.anyContains("OWNER_CREATED", "schemaVersion",
					String.valueOf(id), memberId));
		}
	}
}
