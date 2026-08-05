package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/** cp19 daily-limit, UPDATED by cp20: the create-limit counts owners per adjusted business day. All
 *  owners created now map to the same business day, so 100 creates then the 101st is rejected. */
@Tag("cp19")
class Cp19Tests extends AcceptanceBase {

	@Test
	void coreRejectsOverDailyLimit() throws Exception {
		createMany(100);
		createOwner(ownerNode()).andExpect(status().isTooManyRequests());
	}
}
