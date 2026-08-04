package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;

/** cp17 locality: Derive 'locality' from the city using a city-to-region lookup; return the canonical region... */
@Tag("cp17")
class Cp17Tests extends AcceptanceBase {

	@Test
	void coreDerivesLocality() throws Exception {
		int id = createOwnerOk(ownerNode());
		getOwner(id).andExpect(jsonPath("$.locality").exists()); // unknown city -> "UNKNOWN"
	}
}
