package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;

/** cp20 business-day: The default registration date must now fall on a business day: when the server date is a S... */
@Tag("cp20")
class Cp20Tests extends AcceptanceBase {

	@Test
	void coreRegistrationRollsToBusinessDay() throws Exception {
		int id = createOwnerOk(ownerNode());
		getOwner(id).andExpect(jsonPath("$.registrationDate").exists()); // TODO: assert Mon when server date is weekend
	}
}
