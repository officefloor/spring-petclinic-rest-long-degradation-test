package org.springframework.samples.petclinic.acceptance;

import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

/** cp13: reject creating an owner once 20 have already been created today. */
@Tag("cp13")
class Cp13Tests extends AcceptanceBase {

	@Test
	void coreRejectsOverDailyCap() throws Exception {
		for (int i = 0; i < 20; i++) {
			createOwnerOk(ownerNode()); // distinct cities, so the per-city cap is not hit
		}
		createOwner(ownerNode()).andExpect(status().isBadRequest()); // 21st today
	}
}
