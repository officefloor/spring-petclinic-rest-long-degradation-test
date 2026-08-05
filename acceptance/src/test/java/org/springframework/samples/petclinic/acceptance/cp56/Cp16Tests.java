package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;

/** cp16 customer-code-city, UPDATED by cp56: the customerCode field is gone (unified into memberId),
 *  so its city-prefixed format no longer applies. */
@Tag("cp16")
class Cp16Tests extends AcceptanceBase {

	@Test
	void coreCustomerCodeRemoved() throws Exception {
		int id = createOwnerOk(knownOwner("Sydney"));
		getOwner(id).andExpect(jsonPath("$.customerCode").doesNotExist());
	}
}
