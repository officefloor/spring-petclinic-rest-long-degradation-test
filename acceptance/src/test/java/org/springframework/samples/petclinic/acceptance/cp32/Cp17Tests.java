package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;

/** locality: the region derivation shared with the identity is unchanged for a
 * known city/postcode. Sydney (postcode 2000) still resolves locality "NSW". */
@Tag("cp17")
class Cp17Tests extends AcceptanceBase {

	@Test
	void coreLocalityStillRegion() throws Exception {
		int id = createOwnerOk(knownOwner("Sydney"));
		getOwner(id).andExpect(jsonPath("$.locality").value("NSW"));
	}
}
