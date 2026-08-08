package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;

/** customer-code: the customerCode field is removed (its identity role is now
 * the memberId). */
@Tag("cp09")
class Cp09Tests extends AcceptanceBase {

	@Test
	void coreCustomerCodeRemoved() throws Exception {
		int id = createOwnerOk(knownOwner("Sydney"));
		getOwner(id).andExpect(jsonPath("$.customerCode").doesNotExist());
	}
}
