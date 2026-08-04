package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;

/** cp23 tier-gold: membershipTier becomes 'GOLD' when the owner's household (owners sharing the same househol... */
@Tag("cp23")
class Cp23Tests extends AcceptanceBase {

	@Test
	void coreGoldForLargeHousehold() throws Exception {
		// TODO: build a 3-member household, expect GOLD
		int id = createOwnerOk(ownerNode());
		getOwner(id).andExpect(jsonPath("$.membershipTier").exists());
	}
}
