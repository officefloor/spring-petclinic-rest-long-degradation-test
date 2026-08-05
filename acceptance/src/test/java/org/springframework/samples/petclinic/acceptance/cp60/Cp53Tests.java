package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** cp53 audit-event, UPDATED by cp60: the structured event moves to schema version 2, adding a
 *  'schemaVersion' of 2 while still carrying the OWNER_CREATED marker and the owner id. */
@Tag("cp53")
class Cp53Tests extends AcceptanceBase {

	@Test
	void coreEventIsSchemaV2() throws Exception {
		try (AuditLogCapture audit = new AuditLogCapture()) {
			int id = createOwnerOk(structuredOwner());
			assertTrue(audit.anyContains("OWNER_CREATED", "schemaVersion", String.valueOf(id)));
		}
	}
}
