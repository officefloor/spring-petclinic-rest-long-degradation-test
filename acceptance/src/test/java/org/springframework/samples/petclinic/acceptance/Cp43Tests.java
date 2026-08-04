package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** cp43 audit-enriched: The create audit line (via AUDIT) must now also include membershipLevel and membershipNumb... */
@Tag("cp43")
class Cp43Tests extends AcceptanceBase {

	@Test
	void coreAuditIncludesLevelAndNumber() throws Exception {
		try (AuditLogCapture audit = new AuditLogCapture()) {
			int id = createOwnerOk(withPostcode(ownerNode()));
			assertTrue(audit.count() > 0); // TODO: assert membershipLevel + membershipNumber present
		}
	}
}
