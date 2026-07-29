package org.springframework.samples.petclinic.acceptance;

import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

/** cp08: registrationDate defaults to today when not supplied. */
@Tag("cp08")
class Cp08Tests extends AcceptanceBase {

	@Test
	void coreDefaultsRegistrationDateToToday() throws Exception {
		int id = createOwnerOk(ownerNode());
		getOwner(id).andExpect(jsonPath("$.registrationDate").value(today()));
	}
}
