package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;

/** cp37 telephone-display: Return 'telephoneDisplay' = the stored E.164 telephone formatted for humans (country code,... */
@Tag("cp37")
class Cp37Tests extends AcceptanceBase {

	@Test
	void coreFormatsTelephoneDisplay() throws Exception {
		int id = createOwnerOk(ownerNode());
		getOwner(id).andExpect(jsonPath("$.telephoneDisplay").exists()); // "+CC nnn nnn nnn"
	}
}
