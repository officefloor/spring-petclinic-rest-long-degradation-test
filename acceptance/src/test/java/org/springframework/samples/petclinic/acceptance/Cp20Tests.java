package org.springframework.samples.petclinic.acceptance;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import tools.jackson.databind.node.ObjectNode;

/** cp20: WARN to AUDIT when a new owner's area code (first 3 digits) is shared by 5+ existing owners. */
@Tag("cp20")
class Cp20Tests extends AcceptanceBase {

	private void createWithAreaCode(String area) throws Exception {
		ObjectNode o = ownerNode();
		o.put("telephone", String.format(area + "%07d", seq())); // unique 10-digit, shared 3-digit area
		createOwnerOk(o);
	}

	@Test
	void coreWarnsOnBulkAreaCode() throws Exception {
		try (AuditLogCapture audit = new AuditLogCapture()) {
			for (int i = 0; i < 5; i++) {
				createWithAreaCode("571");
			}
			createWithAreaCode("571"); // 6th — now 5 existing share the area code
			assertTrue(audit.anyAtLevel("WARN"),
					"expected a WARN audit for a bulk signup; got " + audit.messages());
		}
	}

	@Test
	void functionalityNoWarnBelowThreshold() throws Exception {
		try (AuditLogCapture audit = new AuditLogCapture()) {
			createWithAreaCode("572");
			createWithAreaCode("572");
			createWithAreaCode("572"); // only 2 existing share the area code
			assertFalse(audit.anyAtLevel("WARN"),
					"no WARN expected when fewer than 5 owners share the area code");
		}
	}
}
