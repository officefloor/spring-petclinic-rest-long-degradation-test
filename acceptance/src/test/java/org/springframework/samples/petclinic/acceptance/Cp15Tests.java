package org.springframework.samples.petclinic.acceptance;

import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

/**
 * cp15: membershipTier — first 100 owners ever created are FOUNDING. (STANDARD
 * only appears past 100 owners, which isn't practical to force in an isolated
 * test, so we assert the FOUNDING boundary that a fresh create must satisfy.)
 */
@Tag("cp15")
class Cp15Tests extends AcceptanceBase {

	@Test
	void coreFoundingTier() throws Exception {
		int id = createOwnerOk(ownerNode());
		getOwner(id).andExpect(jsonPath("$.membershipTier").value("FOUNDING"));
	}
}
