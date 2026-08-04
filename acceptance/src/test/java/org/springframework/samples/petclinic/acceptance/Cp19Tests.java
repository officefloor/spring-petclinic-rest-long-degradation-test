package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/** cp19 daily-limit: Reject creating an owner when 100 or more owners have already been created today (by regis... */
@Tag("cp19")
class Cp19Tests extends AcceptanceBase {

	@Test
	void coreRejectsOver100Today() throws Exception {
		// TODO: reach 100 creates today, then expect 429
		createOwner(ownerNode()).andExpect(status().is2xxSuccessful()); // placeholder
	}
}
